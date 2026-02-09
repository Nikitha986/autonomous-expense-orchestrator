from mcp_server.tools.policy import policy_check

expense = {
    "date": "21-11-2025",
    "vendor": "Reliance Smart",
    "amount": 6000
}

print("First call:")
print(policy_check(expense))

print("\nSecond call (duplicate):")
print(policy_check(expense))
