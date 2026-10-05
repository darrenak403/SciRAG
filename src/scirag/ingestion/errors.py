class PermanentIngestionError(Exception):
    """The paper cannot be ingested as it is; trying again will not help.

    code is stored on the paper and message is shown to its owner.
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class PaperGone(Exception):
    """The paper was deleted while it was being processed. Nothing is left to do."""
