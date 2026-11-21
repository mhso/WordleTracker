# Approach
## On program start-up
Load missing historic messages from official Wordle bot. Only look at day-after summary messsages
and save scores to database.

## When official Wordle bot posts or edits

### Message is a live update
Look at database:
- if player has no entry for that day, insert one
- if player has an entry, update it with new score
- if a new player is grouped with a previous player, insert/update both

## Message is a day-after summary
Look at database:
- if scores aren't reflected in the database, update them