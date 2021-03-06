# -*- coding: utf-8 -*-
# Copyright (c) 2014 Soren Bjornstad <contact@sorenbjornstad.com>
# License: GNU AGPL, version 3 or later; see COPYING for details

import ui.termdisplay
import database
import entries
import notebooks
import utilities

### OCCURRENCES ###
def occurrences_around(ntype, nnum, page, margin=1):
    """
    Find other entries that are used on the same or a nearby page.

    Arguments:
    - ntype, nnum, page to look around. Page must be an int or we will crash.
    - (optional) Margin of nearby pages to look at as well. This will find
      ranges. Default value is 1.

    Returns a list of (page, entry) tuples sorted first numerically by page,
    then alphabetically by entry.
    """

    # find the nid of the notebook containing the entry we're looking at
    nid = notebooks.get_nid(ntype, nnum)

    # what page range are we looking at?
    pageLow = page - margin
    pageHigh = page + margin

    # pad with leading zeroes to let this feature work with low numbers
    pageLow = utilities.zero_pad(str(pageLow), ntype)
    pageHigh = utilities.zero_pad(str(pageHigh), ntype)

    # find occurrences in same notebook with similar pages; surprisingly,
    # BETWEEN works perfectly on strings, and even finds ranges (on the high
    # end only)
    database.cursor.execute('SELECT eid, page FROM occurrences \
                    WHERE nid = ? AND page BETWEEN ? AND ?',\
                    (nid, pageLow, pageHigh))

    # now find what entries they belong to
    results = []
    counter = 0
    for i in database.cursor.fetchall():
        database.cursor.execute('SELECT name FROM entries WHERE eid = ?', (i[0],))
        results.append((i[1], database.cursor.fetchall()[0][0]))
        counter += 1

    # I don't have the slightest idea what this is doing, but it implements the
    # sort I want: first by page number, then alphabetically (non-case-
    # sensitively) by entry
    # http://stackoverflow.com/questions/2494740/sort-a-list-of-tuples-without-case-sensitivity
    results.sort(key=lambda t : tuple(s.lower() if \
                        isinstance(s,basestring) else s for s in t))

    return results

def add_occurrence(entry, ntype, nnum, pagenum):
    """
    Create a new occurrence, adding the entry if it does not already exist.
    The arguments should be obvious from the declaration.
    
    This function does *not* commit the changes for performance reasons; the
    calling function should handle doing it when convenient so the changes are
    not lost if the program crashes.

    The notebook specified must exist.

    Return True if it works, False if the occurrence already existed.
    """

    # get notebook ID
    database.cursor.execute('SELECT nid FROM notebooks WHERE ntype = ? AND nnum = ?', (ntype, nnum))
    nid = database.cursor.fetchall()[0][0]
    if not nid:
        termdisplay.warn("That notebook does not exist!")
        return False

    # get entry eid if entry exists; add it if it does not
    eid = entries.get_eid(entry)
    if not eid:
        database.cursor.execute('INSERT INTO entries VALUES (null, ?)', (entry,))
        eid = entries.get_eid(entry) # now we can get it

    # enter occurrence for entry unless it already exists
    database.cursor.execute('SELECT oid FROM occurrences WHERE \
            page=? AND nid=? AND eid=?', (pagenum,nid,eid))
    if not database.cursor.fetchall():
        database.cursor.execute('INSERT INTO occurrences VALUES (null, ?, ?, ?)', (pagenum, nid, eid))
        return True
    else:
        return False

def fetch_occurrences(eid):
    """
    Given an EID, get occurrences that match it.

    Return occurrence locations in the form of a list of tuples 
    (ntype, nnum, page).
    """

    database.cursor.execute('SELECT occurrences.nid, occurrences.page FROM occurrences \
                    WHERE eid = ?', (eid,))

    # Loop over list of occurrences that reference entry. Store each match's ref
    # in a dictionary using a match_num ID used only here.
    matches = []
    for i in database.cursor.fetchall():
        nid, pagenum = i
        database.cursor.execute('SELECT notebooks.ntype, notebooks.nnum FROM notebooks \
                        WHERE nid = ?', (nid,))
        ntype, nnum = database.cursor.fetchall()[0]

        matches.append((ntype, nnum, pagenum))

    # sort in order placed: by type, notebook num, page num
    # unfortunately, does alphabetical sort on numbers in pagenums, as that field
    # must be a string because of ranges and parens and sees
    # we can mitigate this by requiring leading zeroes when adding
    matches.sort()
    return matches

### ENTRIES ###
def get_eid(entry):
    """Given an entry's name, return its eid, or None if entry does not exist."""

    database.cursor.execute('SELECT eid FROM entries WHERE name = ?;', (entry,))
    eid = database.cursor.fetchall()
    if eid:
        return eid[0][0]
    else:
        return None

def correct_entry(entry, new_entry):
    """
    Modify the text of an entry to correct typos or the like.
    Arguments: the current text of the entry to change and the new value for the text.
    """

    database.cursor.execute('UPDATE entries SET name = ? WHERE name = ?',
                            (new_entry, entry))

def coalesce_entry(from_entry, to_entry, redir=True):
    """
    Combine two entries by moving all the occurrences from the 'from' into the
    'to', then creating a "moved to" occurrence and changing the 'from' entry
    to point to that.

    Arguments: the 'from' and 'to' entries. Make sure they both exist first.
    Optional argument: redir. If True, we will leave a "moved to" message at
    the 'from' entry; otherwise we will wipe the 'from' entry from the database
    entirely.
    """

    # gather all needed information before we start changing anything
    from_eid = entries.get_eid(from_entry)
    to_eid = entries.get_eid(to_entry)
    if redir:
        occ_list = fetch_occurrences(from_eid)
        from_ntype, from_nnum, from_page = occ_list[0]
        from_pagenum = "moved to " + to_entry.upper()

    # make changes
    database.cursor.execute('UPDATE occurrences SET eid = ? WHERE eid = ?',
                            (to_eid, from_eid))
    database.cursor.execute('DELETE FROM occurrences WHERE eid = ?',
                            (from_eid,))
    if redir:
        add_occurrence(from_entry, from_ntype, from_nnum, from_pagenum)
    else:
        delete_entry(from_eid)

def delete_entry(eid):
    """
    Delete an entry and any associated occurrences.
    """

    database.cursor.execute('DELETE FROM occurrences WHERE eid = ?', (eid,))
    database.cursor.execute('DELETE FROM entries WHERE eid = ?', (eid,))
