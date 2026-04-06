"""FundOps Learning Infrastructure.

Cross-cutting learning that connects all agents. Three speeds:
- Fast: user feedback on screener results (immediate)
- Medium: outcome tracking at 90/180/365d intervals (weeks-months)
- Slow: bias detection from 200+ resolved outcomes (months-years)

This module implements Loop 1 (preference alignment) and Loop 2
(behavioral calibration). Loop 3 (outcome reinforcement) activates
once enough outcome data accumulates.
"""
