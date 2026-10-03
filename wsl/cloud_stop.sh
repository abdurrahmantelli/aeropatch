#!/bin/bash
pkill -f local_cloud_server.py 2>/dev/null && echo "CLOUD_STOPPED" || echo "CLOUD_NOT_RUNNING"