class DatabaseError(Exception):
    pass


class RecordNotFoundError(DatabaseError):
    pass


class ConnectionError(DatabaseError):
    pass


class SchemaError(DatabaseError):
    pass
