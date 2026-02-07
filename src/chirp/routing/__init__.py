"""Routing — compiled route table with O(path-depth) matching.

Routes are registered during setup and compiled into an immutable
lookup structure when the app freezes.
"""
