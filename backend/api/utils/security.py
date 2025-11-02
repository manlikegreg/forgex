import shlex
from typing import List

# Allowed tools and starters
ALLOWED_TOOLS = {
    'pyinstaller', 'pip', 'python', 'pkg', 'nexe', 'go', 'cargo', 'javac', 'jar', 'jpackage', 'dotnet', 'makensis'
}

# Very dangerous tokens/payloads to block
BLACKLIST_TOKENS = [
    'rm -rf /', ':(){ :|: & };:', '>& /dev/sda', 'mkfs', 'format C:', 'shutdown', 'reboot', 'curl http://', 'wget http://'
]


def validate_command(cmd: List[str]) -> bool:
    """Ensure first token is an allowed tool and the command doesn't contain dangerous patterns."""
    if not cmd:
        return False
    tool = cmd[0]
    base = tool.split('/')[-1].split('\\')[-1]
    base = base.lower().replace('.exe','')
    if base not in ALLOWED_TOOLS:
        return False
    joined = ' '.join(shlex.quote(c) for c in cmd)
    for bad in BLACKLIST_TOKENS:
        if bad in joined:
            return False
    return True
