class BatchRenameError(Exception):
    pass

class PatternError(BatchRenameError):
    pass

class SanitizeError(BatchRenameError):
    pass

class ConfigError(BatchRenameError):
    pass
