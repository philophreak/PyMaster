# PyMaster
# Copyright (C) 2014, 2015 FreedomOfRestriction <FreedomOfRestriction@openmailbox.org>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import datetime
import time
import random

import pymasterlib as lib
from pymasterlib.constants import *


def load_text(ID):
    return lib.message.load_text("request", ID)


def get_time_limit(activity):
    """Return the time limit of the activity if it exists, None otherwise."""
    activity_d = lib.activities_dict.get(activity, {})
    if "time_limit" in activity_d:
        time_limit = eval(activity_d["time_limit"])

        if time_limit is not None:
            time_deviate = random.uniform(-1, 1)
            max_ = eval(activity_d.get("time_limit_max", repr(time_limit)))
            min_ = eval(activity_d.get("time_limit_min", repr(time_limit)))
            if time_deviate > 1:
                time_limit += (max_ - time_limit) * time_deviate
            elif time_deviate < 1:
                time_limit += (time_limit - min_) * time_deviate

        return time_limit
    else:
        return None


def get_allowed(activity):
    """Return whether or not the activity is allowed."""
    activity_d = lib.activities_dict.get(activity, {})
    flags = activity_d.get("flags", [])
    lib.slave.forget()

    if lib.slave.sick:
        if "sick_accept" in flags:
            return True
        elif "sick_deny" in flags:
            return False

    if lib.slave.bedtime is None or "night_possible" in flags:
        last_time = None
        for a in lib.slave.activities.setdefault(activity, []):
            if last_time is None or a > last_time:
                last_time = a

        interval = eval(activity_d.get("interval", "0"))
        interval_good = eval(activity_d.get("interval_good", repr(interval)))
        nchores = len(lib.slave.chores) - len(lib.slave.abandoned_chores)
        chore_bonus = 1 / ((interval / interval_good) ** (1 / CHORES_TARGET))
        interval *= chore_bonus ** max(nchores, 0)
        limit = activity_d.get("limit")
        for i in lib.slave.misdeeds:
            for misdeed in lib.slave.misdeeds[i]:
                if misdeed.get("punished", False):
                    penalty = MISDEED_PUNISHED_PENALTY
                elif i in lib.misdeeds_dict:
                    penalty = lib.misdeeds_dict[i].get("penalty", 1)
                else:
                    penalty = lib.activities_dict.get(i, {}).get("penalty", 1)

                interval *= penalty

        if ((limit is None or len(lib.slave.activities[activity]) < limit) and
                (last_time is None or time.time() >= last_time + interval)):
            return True

    return False


def request(activity):
    """
    Request the activity ``activity`` and return whether permission is
    granted.  Same as get_allowed, but also adds the activity as done.
    """
    if get_allowed(activity):
        lib.slave.add_activity(activity)
        return True
    else:
        return False


def allow_timed(activity, m=None):
    """Allow ``activity`` with a time limit, indicating the message ``m``."""
    time_limit = get_time_limit(activity)
    time_limit_text = lib.message.get_printed_time(time_limit, True)
    if m:
        m = ''.join([m, load_text("time_limit")]).format(time_limit_text)
    else:
        m = load_text("time_limit").format(time_limit_text)
    a = [lib.message.load_text("phrases", "finished")]
    if lib.message.get_interruption(m, time_limit, a) is None:
        lib.message.beep()
        m = load_text("time_up")
        a = lib.message.load_text("phrases", "assent")
        time_passed = lib.message.get_time(m, a)
        if time_passed > ONE_MINUTE:
            lib.message.show(load_text("too_long"))
            for _ in range(0, int(time_passed), int(time_limit)):
                lib.assign.punishment(activity)


def allow(ID, activity, msg, other_ID=None):
    flags = activity.get("flags", [])
    if lib.slave.sick and "sick_accept" in flags:
        lib.message.show(msg, lib.message.load_text("phrases", "thank_you"))
    else:
        other = lib.activities_dict.get(other_ID, {})
        script = activity.get("script") or other.get("script")
        if script:
            lib.message.show_timed(msg, 5)
            eval(script)()
        elif "time_limit" in activity:
            allow_timed(ID, msg)
        else:
            a = lib.message.load_text("phrases", "thank_you")
            lib.message.show(msg, a)


def deny(ID, activity):
    flags = activity.get("flags", [])
    if lib.slave.sick and "sick_deny" in flags:
        m = load_text("{}_sick".format(ID))
        if not m:
            m = load_text("{}_deny".format(ID))
        a = lib.message.load_text("phrases", "assent")
        lib.message.show(m, a)
    else:
        m = load_text("{}_deny".format(ID))
        if "can_beg" in flags:
            a = [lib.message.load_text("phrases", "assent"),
                 load_text("beg_{}".format(ID))]
            if lib.message.get_choice(m, a, 0):
                if request("__beg"):
                    if random.randrange(100) < BEG_GAME_CHANCE:
                        m = load_text("beg_{}_accept_game".format(ID))
                        a = lib.message.load_text("phrases", "assent")
                        lib.message.show(m, a)
                        lib.scripts.wait_game("taunt_{}".format(ID))
                        m = load_text("beg_{}_game_win".format(ID))
                        allow(ID, activity, m)
                    else:
                        m = load_text("beg_{}_accept".format(ID))
                        allow(ID, activity, m)
                else:
                    m = load_text("beg_{}_deny".format(ID))
                    a = lib.message.load_text("phrases", "assent")
                    lib.message.show(m, a)
        else:
            a = lib.message.load_text("phrases", "assent")
            lib.message.show(m, a)


def what():
    m = load_text("ask_what")
    c = []
    for i, activity in lib.activities:
        if i not in SPECIAL_ACTIVITIES:
            c.append(load_text("choice_{}".format(i)))
        else:
            break
    c.append(load_text("special_choice_bed"))
    c.append(load_text("special_choice_new_chore"))
    c.append(load_text("special_choice_nothing"))
    choice = lib.message.get_choice(m, c, len(c) - 1)

    if choice < len(c) - 3:
        ID, activity = lib.activities[choice]
        other_ID = activity.get("other_activity")
        flags = activity.get("flags", [])
        if other_ID:
            other_activity = lib.activities_dict[other_ID]
            if get_allowed(ID):
                m = load_text("{}_ask_{}".format(ID, other_ID))
                if lib.message.get_bool(m):
                    if request(other_ID):
                        lib.slave.add_activity(ID)
                        m = load_text("{}_accept_with_{}".format(ID, other_ID))
                        allow(ID, activity, m, other_ID)
                    else:
                        m = load_text("{}_deny_{}".format(ID, other_ID))
                        lib.message.show(m)
                else:
                    lib.slave.add_activity(ID)
                    m = load_text("{}_accept_no_{}".format(ID, other_ID))
                    allow(ID, activity, m)
            else:
                deny(ID, activity)
        else:
            if request(ID):
                m = load_text("{}_accept".format(ID))
                allow(ID, activity, m)
            else:
                deny(ID, activity)
    elif choice == len(c) - 3:
        lib.scripts.evening_routine()
    elif choice == len(c) - 2:
        if lib.slave.bedtime is None:
            if not lib.slave.sick:
                if lib.slave.queued_chore is None:
                    lib.message.show(load_text("chore_assign"))
                    lib.assign.chore()
                else:
                    lib.message.show(load_text("chore_already_assigned"))
            else:
                lib.message.show(load_text("chore_sick_no"))
        else:
            lib.message.show(load_text("chore_night_no"))
