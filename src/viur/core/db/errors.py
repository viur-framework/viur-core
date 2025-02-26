"""This file provides viur.datastore exception/error hierarchy.

We are mapping the error status of the rest api to that hierarchy in
CANONICAL_ERROR_CODE_MAP.
"""
import json
import logging
import requests
from .config import conf


class ViurDatastoreError(ValueError):
    """Base Exception class for viur-datastore errors.

    Can be used as a catch all Exception/Error.
    """
    pass


class AbortedError(ViurDatastoreError):
    """Indicates that the request conflicted with another request.

    status code 400

    For a non-transactional commit:
    Retry the request or structure your entities to reduce contention.

    For requests that are part of a transactional commit:
    Retry the entire transaction or structure your entities to reduce contention.
    """
    pass


class CollisionError(ViurDatastoreError):
    """Indicates that the request attempted to insert an entity that already exists.

    This error/exception was problabely catched at most 3 times with exponential backoff.

    Eventually we can assume, that this error/failure should be accepted.

    status code 409

    Do not retry without fixing the problem.
    """
    pass


class DeadlineExceededError(ViurDatastoreError):
    """A deadline was exceeded on the server.

    status code 504

    Retry using exponential backoff.
    """
    pass


class FailedPreconditionError(ViurDatastoreError):
    """Indicates that a precondition for the request was not met.

    The message field in the error response provides information about the precondition that failed.
    One possible cause is running a query that requires an index not yet defined.

    Do not retry without fixing the problem.

    """
    pass


class InternalError(RuntimeError):
    """Server returned an error.

    status code 500

    Do not retry this request more than once.
    """
    pass


class InvalidArgumentError(ViurDatastoreError):
    """Indicates that a request parameter has an invalid value.

    The message field in the error response provides information as to which value was invalid.

    status code 400

    Do not retry without fixing the problem.
    """
    pass


class NotFoundError(ViurDatastoreError):
    """Indicates that the request attempted to update an entity that does not exist.

    status code 404

    Do not retry without fixing the problem.
    """
    pass


class PermissionDeniedError(ViurDatastoreError):
    """Indicates that the user was not authorized to make the request.

    status code 403

    Do not retry without fixing the problem.
    """
    pass


class ResourceExhaustedError(ViurDatastoreError):
    """Indicates that the project exceeded either its quota or the region/multi-region capacity.

    status code 429

    Verify that you did not exceed your project quota. If you exceeded a project quota,
    do not retry without fixing the problem.

    Otherwise, retry with exponential backoff.
    """
    pass


class UnauthenticatedError(ViurDatastoreError):
    """Indicates that the request did not have valid authentication credentials.

    status code

    Do not retry without fixing the problem.
    """
    pass


class UnavailableError(ViurDatastoreError):
    """Server returned an error.

    status code 503

    Retry using exponential backoff.
    """
    pass


class NoMutationResultsError(ViurDatastoreError):
    """This error indicates that it's either an internal bug in viur-datastore or the datastore itself went bust

    This is an 'internal' error which is not backed by an error code provided by google datastore.
    """
    pass


"""This maps the indicator from error object status field to one of
our ViurDatastore Exception classes"""
CANONICAL_ERROR_CODE_MAP = {
    "ABORTED": AbortedError,
    "ALREADY_EXISTS": CollisionError,
    "DEADLINE_EXCEEDED": DeadlineExceededError,
    "FAILED_PRECONDITION": FailedPreconditionError,
    "INTERNAL": InternalError,
    "INVALID_ARGUMENT": InvalidArgumentError,
    "NOT_FOUND": NotFoundError,
    "PERMISSION_DENIED": PermissionDeniedError,
    "RESOURCE_EXHAUSTED": ResourceExhaustedError,
    "UNAUTHENTICATED": UnauthenticatedError,
    "UNAVAILABLE": UnavailableError
}
