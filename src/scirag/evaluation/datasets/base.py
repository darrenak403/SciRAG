"""What a dataset gives the runner: papers to index and questions to ask of them."""

from dataclasses import dataclass, field

from scirag.parsing.document import ScientificDocument
from scirag.rag.types import Mode


@dataclass(frozen=True)
class EvalPaper:
    # Stable name of the paper inside its dataset; the indexed copy is found by it.
    key: str
    title: str
    document: ScientificDocument


@dataclass(frozen=True)
class EvalQuestion:
    id: str
    text: str
    # The papers the question is asked of.
    paper_keys: list[str]
    # Passages that hold the answer, as text. Empty for a question the papers cannot answer.
    evidence: list[str]
    reference: str | None
    answerable: bool = True
    kind: str = "factual"
    # The path that answers it: one answer, a table over the papers, or a review across them.
    mode: Mode = "factual"
    # Papers an answer should draw on, for a question asked of many. Empty: not scored.
    expected_papers: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EvalDataset:
    name: str
    papers: dict[str, EvalPaper]
    questions: list[EvalQuestion] = field(default_factory=list)
