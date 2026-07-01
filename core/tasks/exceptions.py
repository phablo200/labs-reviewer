"""Shared task exceptions."""


class TaskDispatchEnqueueError(Exception):
    """Raised when a task cannot be enqueued."""


class TaskDispatcherConfigurationError(Exception):
    """Raised when task dispatch configuration is invalid."""

