"""AI CPA agent (spec §14).

The agent is a narrator and advisor over deterministic output — never a
calculator. Its cardinal rule:

    The model never produces a number that the engine did not compute.

Every figure in an agent response must trace to a tool result; the agent's
value is interpretation and prioritization, not arithmetic.
"""
