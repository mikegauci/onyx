"""Server-side AI gateway (roadmap PR-013).

Every model call goes through ``AIGateway``: it resolves the configured model, reserves the
worst-case cost against the tenant's monthly budget (failing closed), calls the provider with
a timeout and bounded retries, validates the structured output and records token use and cost
for the tenant. Provider keys stay on the server; prompts and replies are never logged.
"""
