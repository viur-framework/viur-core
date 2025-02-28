"""
    This file just holds some configuration variables that will influence
    the behaviour of this library.
"""
conf = {
    # If set, we'll log each query we run
    "traceQueries": False,

    # A reference to the skeleton container of ViUR. Unless set, fetch() and getSkel() will fail
    "SkeletonInstanceRef": None,
    # an allow list which error codes should trigger a verbose message output on stderr/stdout
    # take a look in viur.datastore.errors.CANONICAL_ERROR_CODE_MAP keys and the Exceptions for reference
    "verbose_error_codes": {
        "ABORTED",
        "ALREADY_EXISTS",
        "DEADLINE_EXCEEDED",
        "FAILED_PRECONDITION",
        "INTERNAL",
        "INVALID_ARGUMENT",
        "NOT_FOUND",
        "PERMISSION_DENIED",
        "RESOURCE_EXHAUSTED",
        "UNAUTHENTICATED",
        "UNAVAILABLE"
    },
    # A Client form the Google Memcache Library.
    "memcache_client": None,
}
