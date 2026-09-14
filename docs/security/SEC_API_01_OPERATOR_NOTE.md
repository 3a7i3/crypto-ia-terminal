# Operator note

SEC-API-01 never requires opening, printing, copying, rotating or deleting the
real `.env.secrets` file. Runtime certification inspects only variable names
and empty/non-empty state through `/proc/<pid>/environ`.
