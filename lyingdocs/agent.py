"""DocentAgent: autonomous documentation-code misalignment detection agent."""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path

from .codex import find_codex_binary
from .doctree import DocTree
from .llm import call_llm, call_llm_with_tools, make_client
from .tools import TOOL_SCHEMAS, ToolExecutor
from .workspace import Workspace

logger = logging.getLogger("lyingdocs")

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


class DocentAgent:
    """Autonomous agent that traverses documentation and dispatches code audits."""

    def __init__(
        self,
        config: dict,
        doc_path: Path,
        code_path: Path,
        output_dir: Path,
    ):
        self.config = config
        self.doc_path = doc_path
        self.code_path = code_path
        self.output_dir = output_dir

        self.client = make_client(config)
        self.model = config["model"]
        self.max_iterations = config.get("max_iterations", 50)
        self.token_budget = config.get("token_budget", 524_288)

        self.doctree = DocTree(doc_path)
        self.workspace = Workspace(
            output_dir, max_dispatches=config.get("max_dispatches", 20)
        )

        # Resolve codex binary once at startup
        self.codex_bin = None
        if config.get("codex_enabled", True):
            self.codex_bin = find_codex_binary(config)
            if self.codex_bin:
                logger.info("Codex CLI found: %s", self.codex_bin)
            else:
                logger.warning(
                    "Codex CLI not found. Code analysis dispatches will be unavailable. "
                    "Install via: npm install -g @openai/codex"
                )
        else:
            logger.info("Codex CLI disabled by configuration.")

        self.tool_executor = ToolExecutor(
            doc_root=doc_path,
            code_path=code_path,
            output_dir=output_dir,
            workspace=self.workspace,
            config=config,
            codex_bin=self.codex_bin,
        )

        self.messages: list[dict] = []

    def run(self) -> str:
        """Execute the full agent loop. Returns the final report path."""
        # Resume from checkpoint if requested
        if self.config.get("resume"):
            self.workspace.load_state()

        # Build doc index
        self.doctree.build_index()
        self.doctree.save_index(self.output_dir)

        # Seed conversation
        system_prompt = self._load_prompt("agent_system.txt")
        kickoff = self._build_kickoff_message()

        self.messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": kickoff},
        ]

        logger.info("DocentAgent started — %d doc files indexed", len(self.doctree.files))

        # Agent loop
        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1
            logger.info("--- Agent iteration %d/%d ---", iteration, self.max_iterations)

            # Call LLM with tools
            response = call_llm_with_tools(
                self.client, self.model, self.messages, TOOL_SCHEMAS
            )

            # Append assistant message
            assistant_msg = self._response_to_message(response)
            self.messages.append(assistant_msg)

            # Handle tool calls (parallel when multiple)
            if response.tool_calls:
                parsed_calls = []
                for tool_call in response.tool_calls:
                    name = tool_call.function.name
                    try:
                        args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        args = {}
                    parsed_calls.append((tool_call, name, args))

                if len(parsed_calls) == 1:
                    # Single tool call — execute directly
                    tc, name, args = parsed_calls[0]
                    logger.info("  Tool call: %s(%s)", name, _truncate(str(args), 100))
                    result = self.tool_executor.execute(name, args)
                    logger.info("  Result: %s", _truncate(result, 200))
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    })
                else:
                    # Multiple tool calls — execute in parallel
                    def _exec(item):
                        tc, name, args = item
                        logger.info("  Tool call: %s(%s)", name, _truncate(str(args), 100))
                        result = self.tool_executor.execute(name, args)
                        logger.info("  Result: %s", _truncate(result, 200))
                        return tc, result

                    with ThreadPoolExecutor(max_workers=len(parsed_calls)) as pool:
                        futures = {
                            pool.submit(_exec, item): item[0].id
                            for item in parsed_calls
                        }
                        results_map = {}
                        for future in as_completed(futures):
                            tc, result = future.result()
                            results_map[tc.id] = result

                    # Append results in original order to keep conversation deterministic
                    for tc, _, _ in parsed_calls:
                        self.messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": results_map[tc.id],
                        })

                # Save state after each batch of tool calls
                self.workspace.save_state()
            else:
                # Text-only response — agent is thinking or done
                if response.content:
                    logger.info("  Agent: %s", _truncate(response.content, 200))

            # Check completion
            if self.workspace.is_complete():
                logger.info("Agent signaled completion.")
                break

            # Budget check
            if self.workspace.is_budget_exhausted():
                logger.warning("Codex dispatch budget exhausted — nudging agent to finalize.")
                self.messages.append({
                    "role": "user",
                    "content": (
                        "Your Codex dispatch budget is exhausted. Please call "
                        "finalize_report now to generate the final report with "
                        "the findings collected so far."
                    ),
                })

            # Context management
            if self._estimate_tokens() > self.token_budget:
                self._compress_context()

            # If no tool calls and not complete, nudge to continue
            if not response.tool_calls and not self.workspace.is_complete():
                self.messages.append({
                    "role": "user",
                    "content": "Continue with the audit. Use your tools to proceed.",
                })
        else:
            logger.warning(
                "Max iterations (%d) reached — auto-finalizing.", self.max_iterations
            )

        # Generate final report
        report_path = self._generate_report()
        self.workspace.save_state()

        return str(report_path)

    def _build_kickoff_message(self) -> str:
        """Build the initial message with doc tree overview."""
        overview = self.doctree.get_overview()
        progress = ""
        if self.workspace.findings or self.workspace.completed_sections:
            progress = (
                "\n\n## Resumed Session\n"
                + self.workspace.get_progress_summary()
            )

        codex_status = (
            f"Codex dispatches available: {self.workspace.dispatches_remaining()}"
            if self.codex_bin
            else "Codex CLI: NOT AVAILABLE — you must rely on documentation analysis only"
        )

        return (
            f"## Documentation to Audit\n\n{overview}\n\n"
            f"## Code Repository\nPath: {self.code_path}\n\n"
            f"## Your Budget\n"
            f"{codex_status}\n"
            f"Max iterations: {self.max_iterations}\n"
            f"{progress}\n\n"
            "Begin your audit. Start by examining the high-priority documentation "
            "files, then formulate targeted questions for Codex."
        )

    def _response_to_message(self, response) -> dict:
        """Convert an OpenAI response message to a serializable dict."""
        msg = {"role": "assistant"}
        if response.content:
            msg["content"] = response.content
        if response.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in response.tool_calls
            ]
        return msg

    def _estimate_tokens(self) -> int:
        """Rough token estimate: ~4 chars per token."""
        total_chars = sum(
            len(json.dumps(m)) for m in self.messages
        )
        return total_chars // 4

    def _compress_context(self) -> None:
        """Compress older messages to stay within token budget."""
        logger.info("  Compressing context (estimated %d tokens)", self._estimate_tokens())

        keep_recent = 8  # Keep last 4 exchanges
        if len(self.messages) <= keep_recent + 1:
            return  # Not enough to compress

        # Extract messages to summarize (skip system prompt)
        old_messages = self.messages[1:-keep_recent]
        if not old_messages:
            return

        # Build a summary request
        summary_input = []
        for m in old_messages:
            role = m.get("role", "unknown")
            content = m.get("content", "")
            if m.get("tool_calls"):
                calls = [
                    f'{tc["function"]["name"]}({_truncate(tc["function"]["arguments"], 80)})'
                    for tc in m["tool_calls"]
                ]
                content = "Tool calls: " + ", ".join(calls)
            if content:
                summary_input.append(f"[{role}] {content}")

        summary_text = "\n".join(summary_input)

        summary = call_llm(
            self.client,
            self.model,
            (
                "Summarize the following agent conversation. Preserve ALL key findings, "
                "decisions, audit results, and which doc sections have been examined. "
                "Be concise but complete — this summary replaces the original messages."
            ),
            summary_text,
        )

        # Replace old messages with summary
        self.messages = [
            self.messages[0],  # system prompt
            self.messages[1],  # kickoff message
            {"role": "user", "content": f"[Context Summary from prior work]\n\n{summary}"},
            *self.messages[-keep_recent:],
        ]

        logger.info(
            "  Context compressed: now %d messages (~%d tokens)",
            len(self.messages), self._estimate_tokens(),
        )

    def _generate_report(self) -> Path:
        """Generate the final Misalignment_Report.md from collected findings."""
        report_path = self.output_dir / "Misalignment_Report.md"

        if not self.workspace.findings:
            report = (
                f"# Documentation-Code Misalignment Report: "
                f"{self.doc_path.name}\n\n"
                "## Executive Summary\n\n"
                "No misalignment findings were detected during the audit. "
                "The documentation appears to be well-aligned with the codebase.\n"
            )
            report_path.write_text(report, encoding="utf-8")
            logger.info("No findings — wrote empty report to %s", report_path)
            return report_path

        # Use LLM to synthesize the report
        synthesis_prompt = self._load_prompt("report_synthesis.txt")
        findings_json = json.dumps(
            [asdict(f) for f in self.workspace.findings], indent=2
        )

        user_content = (
            f"Project: {self.doc_path.name}\n\n"
            f"## Raw Findings ({len(self.workspace.findings)} total)\n\n"
            f"```json\n{findings_json}\n```\n\n"
            f"## Audit Coverage\n"
            f"Sections audited: {len(self.workspace.completed_sections)}\n"
            f"Codex dispatches used: {self.workspace.codex_dispatch_count}\n"
        )

        report = call_llm(
            self.client, self.model, synthesis_prompt, user_content
        )

        report_path.write_text(report, encoding="utf-8")
        logger.info("Final report written to %s (%d chars)", report_path, len(report))
        return report_path

    def _load_prompt(self, filename: str) -> str:
        return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "... (truncated)"
