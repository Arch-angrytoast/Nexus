import re

with open('cogs/automod.py', 'r') as f:
    content = f.read()

# Let's inspect the automod file to see if I actually missed adding the is_enabled checks
print("Checking automod checks presence:")
print(content.find('def is_enabled'))

# Ah, it looks like my previous patch `patch_automod_toggles.py` was executed, but wait, the reviewer says they are not respected.
# Let's read the current contents to be absolutely sure.
