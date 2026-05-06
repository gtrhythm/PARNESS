"""PDF-Extract-Kit long-running daemon.

Splits the PEK lifecycle into start / parse / stop so model weights stay
resident across many parse requests, instead of paying the cold-start
cost in every orchestrator subprocess.
"""
