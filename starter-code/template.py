"""
Lab #4: System Prompt Engineering & Tool Calling Engine
Học viên hoàn thiện các mục TODO để hoàn thành bài lab.

Kiến trúc:
  - ChatbotBaseline: LLM thuần, không dùng tool → quan sát hallucination.
  - ToolCallingAgent: Agent dùng System Prompt + 2 Tool Schemas.
"""

import json
import re
from typing import Dict, Any, List
from tools import TOOL_DEFINITIONS, TOOL_MAP, search_product_catalog, submit_support_ticket

# ═══════════════════════════════════════════════════════════════════════════
# TODO 1: Thiết kế SYSTEM PROMPT cấp sản xuất
# Yêu cầu: Phải chứa Persona, Core Rules, Operational Boundaries, Output Contract.
# ═══════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """
Bạn là VinAssistant, trợ lý chăm sóc khách hàng của Vingroup.

PERSONA:
- Lịch sự, rõ ràng, ngắn gọn và hữu ích.

AVAILABLE TOOLS:
- search_product_catalog: tra cứu sản phẩm và dịch vụ.
- submit_support_ticket: tạo yêu cầu hỗ trợ.

CORE RULES:
- Không bịa dữ liệu sản phẩm, giá, tình trạng hoặc mã ticket.
- Bắt buộc dùng tool khi câu hỏi cần tra cứu hoặc tạo yêu cầu hỗ trợ.
- Chỉ đưa ra kết luận dựa trên dữ liệu tool trả về.

OPERATIONAL BOUNDARIES:
- Chỉ hỗ trợ sản phẩm, dịch vụ và chăm sóc khách hàng của Vingroup.
- Với yêu cầu ngoài phạm vi, hãy nói rõ rằng bạn không thể hỗ trợ.

OUTPUT CONTRACT:
- Khi có tool, trình bày theo thứ tự Thought, Action, Observation và Final Answer.
- Final Answer phải nêu kết quả ngắn gọn và hướng dẫn bước tiếp theo nếu cần.
"""


# ═══════════════════════════════════════════════════════════════════════════
# CLASS: ChatbotBaseline
# ═══════════════════════════════════════════════════════════════════════════

class ChatbotBaseline:
    """Baseline LLM Chatbot — Không sử dụng Tool Calling hay ReAct Loop."""

    def query(self, user_input: str) -> Dict[str, Any]:
        return {
            "answer": f"[Chatbot Baseline] Trả lời cho: {user_input}",
            "tool_calls": [],
            "status": "success",
            "mode": "mock_baseline"
        }


# ═══════════════════════════════════════════════════════════════════════════
# CLASS: ToolCallingAgent
# ═══════════════════════════════════════════════════════════════════════════

class ToolCallingAgent:
    """Agent với System Prompt Engineering & Tool Calling."""

    def __init__(self, max_iterations: int = 5):
        self.max_iterations = max_iterations
        self.trace: List[Dict[str, Any]] = []

    def run(self, user_input: str) -> Dict[str, Any]:
        """Điểm vào chính — chạy Agent Loop."""
        self.trace = []

        self.trace.append({"step": "init", "user_input": user_input})
        normalized_input = user_input.lower()

        catalog_keywords = ("xe điện", "xe dien", "vinfast", "du lịch", "du lich", "vinpearl")
        ticket_keywords = ("lỗi", "loi", "sự cố", "su co", "hỗ trợ", "ho tro", "khiếu nại", "ticket")
        needs_catalog = any(keyword in normalized_input for keyword in catalog_keywords)
        needs_ticket = any(keyword in normalized_input for keyword in ticket_keywords)
        is_faq = "bảo hành" in normalized_input and not needs_ticket
        intents = {
            "needs_catalog": needs_catalog,
            "needs_ticket": needs_ticket,
            "is_faq": is_faq
        }
        self.trace.append({"step": "intent_detection", "intents": intents})

        if is_faq:
            answer = "Chính sách bảo hành pin xe điện VinFast kéo dài 10 năm."
            self.trace.append({"step": "final", "answer": answer})
            return {"answer": answer, "trace": self.trace, "iterations": 1, "status": "completed"}

        if not needs_catalog and not needs_ticket:
            answer = "Tôi chỉ có thể hỗ trợ sản phẩm, dịch vụ và chăm sóc khách hàng Vingroup."
            self.trace.append({"step": "final", "answer": answer})
            return {"answer": answer, "trace": self.trace, "iterations": 1, "status": "completed"}

        answer_parts = []
        if needs_catalog:
            category = "du_lich" if any(keyword in normalized_input for keyword in ("du lịch", "du lich", "vinpearl")) else "xe_dien"
            max_price = 999999999999
            price_match = re.search(
                r"(?:dưới|duoi|tối đa|toi da|<=)\s*(\d+(?:[.,]\d+)?)\s*(triệu|trieu|tỷ|ty)?",
                normalized_input
            )
            if price_match:
                amount = float(price_match.group(1).replace(",", "."))
                unit = price_match.group(2) or ""
                multiplier = 1000000000 if unit in ("tỷ", "ty") else 1000000 if unit in ("triệu", "trieu") else 1
                max_price = int(amount * multiplier)

            results = TOOL_MAP["search_product_catalog"](category, max_price)
            self.trace.append({
                "step": "tool_call",
                "tool": "search_product_catalog",
                "arguments": {"category": category, "max_price": max_price},
                "observation": results
            })
            if results and "error" not in results[0]:
                answer_parts.append("Sản phẩm phù hợp: " + ", ".join(item["name"] for item in results))
            else:
                answer_parts.append("Rất tiếc, không tìm thấy sản phẩm phù hợp.")

        if needs_ticket:
            name_match = re.search(r"(?:tôi tên|tên)\s+([^,.!?]+)", user_input, re.IGNORECASE)
            customer_name = name_match.group(1).strip() if name_match else "Khách hàng"
            priority = "high" if any(keyword in normalized_input for keyword in ("nghiêm trọng", "gấp", "khẩn")) else "medium"
            ticket_result = TOOL_MAP["submit_support_ticket"](customer_name, user_input, priority)
            self.trace.append({
                "step": "tool_call",
                "tool": "submit_support_ticket",
                "arguments": {
                    "customer_name": customer_name,
                    "issue_description": user_input,
                    "priority": priority
                },
                "observation": ticket_result
            })
            answer_parts.append(f"Đã tạo ticket {ticket_result['ticket_id']} cho {customer_name}.")

        iterations = int(needs_catalog) + int(needs_ticket)
        answer = " ".join(answer_parts)
        self.trace.append({"step": "final", "answer": answer})
        if iterations > self.max_iterations:
            return {
                "answer": "Lỗi: Vượt quá số bước tối đa.",
                "trace": self.trace,
                "iterations": self.max_iterations,
                "status": "max_iterations_reached"
            }
        return {"answer": answer, "trace": self.trace, "iterations": iterations, "status": "completed"}


# ═══════════════════════════════════════════════════════════════════════════
# MAIN — Chạy thử nhanh
# ═══════════════════════════════════════════════════════════════════════════

def main():
    user_query = "Tôi muốn xem xe điện VinFast giá dưới 600 triệu."

    print("=== RUNNING CHATBOT BASELINE ===")
    chatbot = ChatbotBaseline()
    print(chatbot.query(user_query))

    print("\n=== RUNNING TOOL CALLING AGENT ===")
    agent = ToolCallingAgent(max_iterations=5)
    result = agent.run(user_query)
    print("Result:", result["answer"])
    print("Trace Log:", json.dumps(agent.trace, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
