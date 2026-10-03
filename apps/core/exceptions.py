class StaleObjectError(Exception):
    """The record changed since the form was opened."""

    def __init__(self, message="This record was changed since you opened it. Review the latest values and try again."):
        super().__init__(message)
        self.messages = [message]


class BusinessRuleError(Exception):
    """A user-facing validation failure raised by a service."""

    def __init__(self, messages):
        if isinstance(messages, str):
            messages = [messages]
        self.messages = list(messages)
        super().__init__(" ".join(self.messages))
