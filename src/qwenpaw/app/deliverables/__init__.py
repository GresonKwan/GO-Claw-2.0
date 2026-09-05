# -*- coding: utf-8 -*-
"""GO CLAW turn deliverables.

Tool integrations import only the small registration helpers from here.  The
helpers intentionally become no-ops outside a console turn so bundled plugins
remain compatible with older hosts.
"""

from .collector import register_candidate, register_published

__all__ = ["register_candidate", "register_published"]
