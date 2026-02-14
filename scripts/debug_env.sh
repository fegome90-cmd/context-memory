#!/bin/bash
# Debug environment variables for hook execution
echo "=== HOOK DEBUG $(date) ===" >> /tmp/cm_hook_env_debug.log
echo "CLAUDE_PLUGIN_ROOT: ${CLAUDE_PLUGIN_ROOT}" >> /tmp/cm_hook_env_debug.log
echo "PWD: $(pwd)" >> /tmp/cm_hook_env_debug.log
echo "WHOAMI: $(whoami)" >> /tmp/cm_hook_env_debug.log
echo "USER: ${USER}" >> /tmp/cm_hook_env_debug.log
echo "HOME: ${HOME}" >> /tmp/cm_hook_env_debug.log
echo "=========================" >> /tmp/cm_hook_env_debug.log
exit 0
