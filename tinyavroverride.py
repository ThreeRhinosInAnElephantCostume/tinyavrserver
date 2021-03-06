#!/bin/python3

    # This file is part of tinyavrprogrammer.

    # tinyavrprogrammer is free software: you can redistribute it and/or modify
    # it under the terms of the GNU General Public License as published by
    # the Free Software Foundation, version 3.

    # tinyavrprogrammer is distributed in the hope that it will be useful,
    # but WITHOUT ANY WARRANTY; without even the implied warranty of
    # MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    # GNU General Public License for more details.

    # You should have received a copy of the GNU General Public License
    # along with tinyavrprogrammer.  If not, see <https://www.gnu.org/licenses/>.

import sys
import os

args = (" ".join(["\"" + it + "\"" if " " in it else it for it in sys.argv[1:]]))
print(args)
chips = [["t85", "attiny85"], ["t45", "attiny45"], ["t25", "attiny25"], ["t84", "attiny84"], ["t13", "attiny13"], ["t13a", "attiny13a"]]
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