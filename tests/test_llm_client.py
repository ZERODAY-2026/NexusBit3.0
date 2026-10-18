from pydantic import BaseModel

from lexlocal.llm.client import OllamaClient


class Out(BaseModel):
    summary: str


def test_truncated_output_is_retried_with_a_larger_budget(monkeypatch):
    budgets = []
    replies = iter([('{"summary": "cut o', {"done_reason": "length"}),
                    ('{"summary": "complete"}', {"done_reason": "stop"})])

    def fake_chat(self, messages, schema, max_tokens, temperature=None, seed=7):
        budgets.append(max_tokens)
        return next(replies)

    monkeypatch.setattr(OllamaClient, "_chat", fake_chat)
    out = OllamaClient(model="x").generate_json("sys", "user", Out, max_tokens=400)
    assert out.summary == "complete"
    assert budgets == [400, 700]
