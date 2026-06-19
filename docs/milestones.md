# Milestones

Tracks progress against the phased plan in [initial_plan.md](../initial_plan.md).

| # | Milestone                                   | Phase | Status |
|---|---------------------------------------------|-------|--------|
| 1 | Assemble arm                                | 1     | ☐ |
| 2 | Identify controller board                   | 1     | ☐ |
| 3 | Connect Mac to arm (serial port found)      | 1     | ☐ |
| 4 | Move one servo from Python                   | 1     | ☐ |
| 5 | Move all servos safely (limits recorded)     | 1     | ☐ |
| 6 | Manual jog CLI                              | 3     | ✅ scaffolded (mock) |
| 7 | Save / load poses                           | 3     | ✅ scaffolded (mock) |
| 8 | Design + print marker holder                | 4     | ☐ |
| 9 | Define home / pen_up / pen_down             | 5     | ☐ needs hardware |
| 10| Draw a line                                 | 5     | ✅ planner + preview |
| 11| Draw a square                               | 5     | ✅ planner + preview |
| 12| Draw SVG star                               | 6     | ✅ loader + preview |
| 13| iPhone photo calibration                    | 7     | ◐ homography + UI scaffolded |
| 14| Import iPhone LiDAR scan                     | 8     | ◐ stub (needs scan deps) |
| 15| Plan 3D painting                            | 9     | ☐ future |

Legend: ✅ done · ◐ partial / scaffolded · ☐ not started

**Software runs end-to-end in mock mode today.** Items marked "needs hardware"
are gated on Phase 1 bring-up: capturing real calibration poses, then validating
the first physical square.
