Kariuss Max Headtracking - game compatibility components

Unmodified Windows binaries and game database from the opentrack
2026.1.0 portable distribution:
  NPClient.dll / NPClient64.dll
  freetrackclient.dll / freetrackclient64.dll
  TrackIR.exe (small background compatibility helper, not the opentrack app)
  games.csv

Project and source: https://github.com/opentrack/opentrack
FreeTrack output: proto-ft/ftnoir_protocol_ft.cpp
Shared-memory ABI: freetrackclient/fttypes.h
Kariuss's adapted rotation smoother uses filter-accela/ and spline/spline.cpp.
Copyright (c) 2012-2019 Stanislaw Halik. Permission to use, copy, modify, and/or
distribute this software for any purpose with or without fee is hereby granted,
provided that the above copyright notice and this permission notice appear
in all copies. THE SOFTWARE IS PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND.
Client source and credit are included in npclient/.
See OPENTRACK-LICENSING.txt and FACETRACKNOIR-COPYING.txt for notices.

Kariuss writes the poses itself and uses no opentrack application process.
Only head rotation is available from Rokid Max; XYZ translations stay at zero.
