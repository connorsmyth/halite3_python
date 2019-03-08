# halite3_python
This is a Python bot that was written for the Halite 3 competition. It came 22nd overall.
https://2018.halite.io/

Halite is a programming/AI competition created/hosted by Two Sigma.	In Halite 3, each game has two or four bots compete against each other to gather resources on the map with the aim of finishing with the most resources. Each player uploads a bot, in their preferred language, that will be played against others.

## Playing a game
To run the code, copy the repo and run one of the "run_game_x.sh" scripts, or on the command line run:
./halite --replay-directory replays/ -vvv --width 32 --height 32 "python3 MyBot.py" "python3 MyBot.py"

## Watching a game
The replay file will be saved out to the replays/ directory. You can watch the video at:
https://2018.halite.io/watch-games

## Strategy
A zonal strategy was used to help coordinate the bots when navigating across the map. Each map was divided into 4x4 zones. Each turn a summary of each zone was calculated that helped describe it, such as, total halite, halite adjusted across local zones, presence of my ships to the local area, presence of enemy ships to local area, etc.

## Walkthrough of script
A class called Coordinator was used to initialise  the Zone objects. 

Each turn the map was read in, the Zone objects were updated and the Ships were initialised (for that turn). 

Dictionaries were used to store information about the ships between turns, this is information like their overall goal, their target Zone, if they have stayed still for multiple turns etc.. Ships without a target zone are allocated one if required. To calculate the best target zone to allocate, the score for each zone is discounted by a % for each ship. It is also discounted by the distance from the ship to the given Zone. This means that ships favour less allocated zones that are close to it.

Next all other players next moves were considered, this was done by playing the ships as if they were mine (allocating a mission for that ship, guessing when they would return to base and otherwise playing semi aggressively).

Potential Dropoffs were calculated, given a certain set of conditions of the game, map and my current position. These factors included if there was an area with a high density of halite far away from everyones shipyard (and any dropoffs that I already have). If I have at least 15 ships on the map, if I've redirected enough ships to the last dropoff I have created.

If there is a potential Dropoff, each turn we check if we should still create a dropoff there. Sometimes a good place is found, but by the time we are ready to place a dropoff, an enemy has already crowded the area and it wouldn't be as valuable to take.

The "preferred directions" of travel for each ship is now calculated, the choice of method depends on wether the ship was looking to harvest halite, or move to a zone/back to base. If harvesting halite, a refined set of all the possible commands over the next 6 moves were considered. (Each ship can stay still or move north, east, south or west). If moving to a target square then the next 4 moves were considered, the path of least resistance in the least possible moves was calculated. This allows us to consider enemy ships as an obstacle and prevents ships getting "stuck" behind an enemy ship. One or two preferred moves were created for each ship.

Next each ship's preferred move is considered, first if two ships are swapping positions the command is written and they are checked off. Each ship's command is attempted 7 times in total, sometimes resorting to their second choice move.

Now we are nearing the end of the turn, the bot considers generating a new ship, if it is safe and if it considers there is not enough ships relative to the amount of halite and amount of time left.

Finally some elements of each ship are saved to a few dictionaries for the next turn, and the list of commands is sent back to the game.

