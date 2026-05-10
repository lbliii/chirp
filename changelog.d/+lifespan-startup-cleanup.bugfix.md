Fixed lifespan startup cleanup so a database connection opened during startup is disconnected when a later startup hook or migration step fails before `lifespan.startup.complete`.
