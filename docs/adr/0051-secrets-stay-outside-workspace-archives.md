# Secrets Stay Outside Workspace Archives

FundOps will keep provider API keys and other secrets in the user's Local Credential Store rather than inside the Local FundOps Workspace or Workspace Archives. The workspace may retain provider choices, capability tiers, connection status, non-secret configuration, and Workspace Secret References so it can request credentials locally. We choose this over embedding secrets in the database or backup package so workspace archives are safer to move, restore, inspect, or share without accidentally exporting live credentials.
