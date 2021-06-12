# This program is free software: you can redistribute it and/or modify
#     it under the terms of the GNU General Public License version 3 as published by
#     the Free Software Foundation.

#     This program is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.

#     You should have received a copy of the GNU General Public License
#     along with this program.  If not, see <https://www.gnu.org/licenses/>

#!/bin/python3
import sys
import os

args = (" ".join(["\"" + it + "\"" if " " in it else it for it in sys.argv[1:]]))
print(args)
chips = [["t85", "attiny85"], ["t45", "attiny45"], ["t25", "attiny25"], ["t84", "attiny84"]]
target = None
for it in chips:
    if("-p " + it[0] in args or "-p " + it[1] in args):
        target = it
        break

if target is None:
    os.system("_avrdude " + args)
    exit(0)

from tinyavrserver import *

err = main(target)
exit(err)