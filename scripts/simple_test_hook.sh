#!/bin/bash
# Simple test hook - just append a timestamp to a log file
echo "HOOK CALLED: $(date)" >> /tmp/cm_hook_simple_test.log
echo "CWD: $(pwd)" >> /tmp/cm_hook_simple_test.log
exit 0
