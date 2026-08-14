import re
import json
from typing import Any, Dict, List, Tuple, Optional
from tools.parser import ToolCallParser


class UniversalStreamNormalizer:
    """
    Production-grade Streaming Lexer and State Machine for LLM tool agents.

    Handles streaming token fragments character-by-character with lookahead buffering:
      1. Swallows <think>, </think>, <thought>, </thought> tags cleanly without leaking tag fragments.
      2. Routes reasoning inside thought tags directly to {"type": "thinking"}.
      3. Swallows hallucinated <tool_response>, <tool>, <tool_call>, <tool_code> tags and echo blocks.
      4. Intercepts and suppresses raw tool JSON blocks (```json ... ``` or {"name": ...} or <tool_call>) so they never leak into the chat.
      5. Emits conversational text cleanly in real time as {"type": "token"}.
      6. Finalizes turns cleanly without duplicate token emissions.
    """

    STATE_NORMAL = 0
    STATE_THINKING = 1
    STATE_TOOL_RESPONSE = 2
    STATE_TOOL_BLOCK = 3

    OPEN_THINK = ("<think>", "<thought>")
    CLOSE_THINK = ("</think>", "</thought>")
    OPEN_TOOL_RESP = ("<tool_response>", "<tool_code>")
    CLOSE_TOOL_RESP = ("</tool_response>", "</tool_code>")
    OPEN_TOOL_CALL = ("<tool_call>", "<tool>", "<tools>")
    CLOSE_TOOL_CALL = ("</tool_call>", "</tool>", "</tools>")
    CONTROL_TAGS = ("<|im_start|>", "<|im_end|>", "<|endoftext|>")
    TOOL_STARTERS = ("```json", "```", '{"name":', '{"action":')

    def __init__(self):
        self.state = self.STATE_NORMAL
        self.lookahead = ""
        self.full_content = ""
        self.tool_buffer = ""
        self.native_thinking = ""

    def feed_native_thinking(self, chunk: str) -> Optional[Dict[str, Any]]:
        """Handles provider-native reasoning streams (Ollama thinking field, DeepSeek, Claude 3.7)."""
        if not chunk:
            return None
        self.native_thinking += chunk
        return {"type": "thinking", "content": chunk}

    @staticmethod
    def _matches_any_prefix(text: str, candidates) -> bool:
        """Checks if text is a non-empty strict prefix of any candidate in candidates."""
        return any(c.startswith(text) for c in candidates if len(text) < len(c))

    def feed_content(self, chunk: str) -> List[Dict[str, Any]]:
        """
        Feeds a chunk of text into the streaming lexer and returns normalized events.
        """
        if not chunk:
            return []

        self.full_content += chunk
        self.lookahead += chunk
        events: List[Dict[str, Any]] = []

        while self.lookahead:
            # 1. State: NORMAL
            if self.state == self.STATE_NORMAL:
                # Check if lookahead starts with an opening thought tag
                matched_open_think = next((t for t in self.OPEN_THINK if self.lookahead.startswith(t)), None)
                if matched_open_think:
                    self.state = self.STATE_THINKING
                    self.lookahead = self.lookahead[len(matched_open_think):]
                    continue
                if self._matches_any_prefix(self.lookahead, self.OPEN_THINK):
                    break

                # Check if lookahead starts with a tool response tag to swallow
                matched_open_tr = next((t for t in self.OPEN_TOOL_RESP if self.lookahead.startswith(t)), None)
                if matched_open_tr:
                    self.state = self.STATE_TOOL_RESPONSE
                    self.lookahead = self.lookahead[len(matched_open_tr):]
                    continue
                if self._matches_any_prefix(self.lookahead, self.OPEN_TOOL_RESP):
                    break

                # Check if lookahead starts with a tool call tag (<tool_call>, <tool>, <tools>)
                matched_open_tc = next((t for t in self.OPEN_TOOL_CALL if self.lookahead.startswith(t)), None)
                if matched_open_tc:
                    self.state = self.STATE_TOOL_BLOCK
                    self.tool_buffer += self.lookahead[len(matched_open_tc):]
                    self.lookahead = ""
                    break
                if self._matches_any_prefix(self.lookahead, self.OPEN_TOOL_CALL):
                    break

                # Swallow stray closing tags or control tokens
                all_stray = (
                    self.CLOSE_THINK
                    + self.CLOSE_TOOL_RESP
                    + self.CLOSE_TOOL_CALL
                    + self.CONTROL_TAGS
                )
                matched_stray = next((t for t in all_stray if self.lookahead.startswith(t)), None)
                if matched_stray:
                    self.lookahead = self.lookahead[len(matched_stray):].lstrip()
                    continue
                if self._matches_any_prefix(self.lookahead, all_stray):
                    break

                # Check if lookahead begins a tool block
                stripped = self.lookahead.lstrip()
                matched_tool = next((t for t in self.TOOL_STARTERS if stripped.startswith(t)), None)
                if matched_tool:
                    self.state = self.STATE_TOOL_BLOCK
                    self.tool_buffer += self.lookahead
                    self.lookahead = ""
                    break
                if any(self._matches_any_prefix(stripped, [t]) for t in self.TOOL_STARTERS):
                    break

                # Normal conversational token for the chat
                char = self.lookahead[0]
                self.lookahead = self.lookahead[1:]
                events.append({"type": "token", "content": char})

            # 2. State: THINKING (inside <think>...</think>)
            elif self.state == self.STATE_THINKING:
                matched_close_think = next((t for t in self.CLOSE_THINK if self.lookahead.startswith(t)), None)
                if matched_close_think:
                    self.state = self.STATE_NORMAL
                    self.lookahead = self.lookahead[len(matched_close_think):].lstrip()
                    continue
                if self._matches_any_prefix(self.lookahead, self.CLOSE_THINK):
                    break

                # Fallback: if model starts tool block without closing think tag
                stripped = self.lookahead.lstrip()
                if any(stripped.startswith(t) for t in self.TOOL_STARTERS + self.OPEN_TOOL_CALL):
                    self.state = self.STATE_TOOL_BLOCK
                    self.tool_buffer += self.lookahead
                    self.lookahead = ""
                    break

                # Consume character as thought
                char = self.lookahead[0]
                self.lookahead = self.lookahead[1:]
                events.append({"type": "thinking", "content": char})

            # 3. State: TOOL_RESPONSE (inside hallucinated <tool_response>...</tool_response>)
            elif self.state == self.STATE_TOOL_RESPONSE:
                matched_close_tr = next((t for t in self.CLOSE_TOOL_RESP if self.lookahead.startswith(t)), None)
                if matched_close_tr:
                    self.state = self.STATE_NORMAL
                    self.lookahead = self.lookahead[len(matched_close_tr):].lstrip()
                    continue
                if self._matches_any_prefix(self.lookahead, self.CLOSE_TOOL_RESP):
                    break
                # Swallow character silently
                self.lookahead = self.lookahead[1:]

            # 4. State: TOOL_BLOCK (inside tool JSON markdown or raw JSON or <tool> tags)
            elif self.state == self.STATE_TOOL_BLOCK:
                # Accumulate all tool characters in buffer and DO NOT emit to chat
                self.tool_buffer += self.lookahead
                self.lookahead = ""
                break

        # Coalesce consecutive single-character events of the same type for network efficiency
        return self._coalesce_events(events)

    def finalize(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Finalizes the turn when stream completes:
        1. Flushes any remaining lookahead characters.
        2. Extracts all tool calls from tool_buffer and full_content.
        3. If tool_buffer contains non-tool markdown/code, emits it as conversational token.
        """
        final_events: List[Dict[str, Any]] = []

        if self.lookahead and self.state != self.STATE_TOOL_BLOCK and self.state != self.STATE_TOOL_RESPONSE:
            all_tags = (
                self.OPEN_THINK
                + self.CLOSE_THINK
                + self.OPEN_TOOL_RESP
                + self.CLOSE_TOOL_RESP
                + self.OPEN_TOOL_CALL
                + self.CLOSE_TOOL_CALL
                + self.CONTROL_TAGS
            )
            if not any(t.startswith(self.lookahead) for t in all_tags):
                evt_type = "thinking" if self.state == self.STATE_THINKING else "token"
                final_events.append({"type": evt_type, "content": self.lookahead})
            self.lookahead = ""

        # Extract all tool calls
        combined_text = self.tool_buffer if self.tool_buffer else self.full_content
        tool_calls = ToolCallParser.extract_tool_calls(combined_text)
        if not tool_calls and combined_text != self.full_content:
            tool_calls = ToolCallParser.extract_tool_calls(self.full_content)

        # If tool_buffer was accumulated because of markdown code or JSON that is NOT a tool call,
        # emit it as conversational tokens to the chat
        if not tool_calls and self.tool_buffer:
            clean_buf = self.extract_clean_final_text(self.tool_buffer)
            if clean_buf:
                final_events.append({"type": "token", "content": clean_buf})

        return self._coalesce_events(final_events), tool_calls

    @staticmethod
    def extract_clean_final_text(text: str) -> str:
        """Strips think tags, tool response tags, control tokens, and raw tool json to obtain clean text."""
        if not text:
            return ""
        cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        cleaned = re.sub(r"<thought>.*?</thought>", "", cleaned, flags=re.DOTALL)
        cleaned = re.sub(r"<tool(?:_response|_code)?>.*?</tool(?:_response|_code)?>", "", cleaned, flags=re.DOTALL)
        cleaned = re.sub(r"<tool(?:_call|s)?>.*?</tool(?:_call|s)?>", "", cleaned, flags=re.DOTALL)
        cleaned = re.sub(r"</?(?:think|thought|tool_response|tool_call|tool_code|tool|tools)>", "", cleaned)
        cleaned = re.sub(r"<\|im_start\|>|<\|im_end\|>|<\|endoftext\|>", "", cleaned)
        cleaned = re.sub(r"```(?:json)?\s*\{\s*\"name\"\s*:\s*.*?\}\s*```", "", cleaned, flags=re.DOTALL)
        return cleaned.strip()

    @staticmethod
    def _coalesce_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Combines consecutive single-character stream events of the same type."""
        if not events:
            return []
        coalesced: List[Dict[str, Any]] = []
        for evt in events:
            if coalesced and coalesced[-1]["type"] == evt["type"]:
                coalesced[-1]["content"] += evt["content"]
            else:
                coalesced.append({"type": evt["type"], "content": evt["content"]})
        return coalesced
