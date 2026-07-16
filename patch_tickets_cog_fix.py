with open('cogs/tickets.py', 'r') as f:
    content = f.read()

import re
content = re.sub(
    r'content = "Use the dropdown below to configure the ticket system.\n\n"\n\s+content \+= f"\*\*Panel Title:\*\* \{title\}\n"\n\s+content \+= f"\*\*Panel Description:\*\* \{desc\}\n',
    r'content = "Use the dropdown below to configure the ticket system.\\n\\n"\n            content += f"**Panel Title:** {title}\\n"\n            content += f"**Panel Description:** {desc}\\n"',
    content
)

with open('cogs/tickets.py', 'w') as f:
    f.write(content)
