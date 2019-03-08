import json
import logging
import sys

from .common import read_input
from . import constants
from .game_map import GameMap, Player
from .positionals import Position
from datetime import datetime
from pathfinding.core.grid import Grid
import numpy as np


class Game:
    """
    The game object holds all metadata pertinent to the game and all its contents
    """
    def __init__(self):
        """
        Initiates a game object collecting all start-state instances for the contained items for pre-game.
        Also sets up basic logging.
        """
        self.turn_number = 0

        # Grab constants JSON
        raw_constants = read_input()
        constants.load_constants(json.loads(raw_constants))

        num_players, self.my_id = map(int, read_input().split())

        logging.basicConfig(
            filename="bot-{}.log".format(self.my_id),
            filemode="w",
            level=logging.DEBUG,
        )

        self.players = {}
        for player in range(num_players):
            self.players[player] = Player._generate()
        self.me = self.players[self.my_id]
        self.game_map = GameMap._generate()
        self.game_missions = {}
        self.total_halite_for_ship = {}
        self.turn_ship_created = {}
        self.min_halite_to_take = 50
        self.average_halite = 50
        self.window_size = 4
        self.dict_positions = {}
        self.destroyed_by_enemy_count = 0
        self.check_for_dropoffs = True
        # self.dict_ship_had_to_wait = {}
        self.still_counts = {}
        self.last_positions = {}

    def ready(self, name):
        """
        Indicate that your bot is ready to play.
        :param name: The name of your bot
        """
        send_commands([name])

    def update_frame(self, coordinator):
        """
        Updates the game object's state.
        :returns: nothing.
        """
        self.turn_number = int(read_input())
        logging.info("=============== TURN {:03} ================".format(self.turn_number))

        for _ in range(len(self.players)):
            player, num_ships, num_dropoffs, halite = map(int, read_input().split())
            self.players[player]._update(num_ships, num_dropoffs, halite)

        turn_start_time = datetime.now()
        arr_dropoffs_and_enemy_shipyards = self.me.get_dropoffs_and_shipyard()
        for player in self.players.values():
            arr_dropoffs_and_enemy_shipyards.append(player.shipyard)

        self.game_map._update(arr_dropoffs_and_enemy_shipyards, coordinator)

        search_space = 3
        for entity in self.me.get_dropoffs_and_shipyard():
            for x in range(-search_space,search_space+1):
                for y in range(-search_space,search_space+1):
                    if abs(x) + abs(y) <= search_space:
                        pos = self.game_map.normalize(entity.position + Position(x,y))
                        self.game_map[pos].close_to_my_dropoff = True

        # Mark cells with ships as unsafe for navigation
        for player in self.players.values():
            for ship in player.get_ships():
                self.game_map[ship.position].mark_unsafe(ship)
                if player.id != self.me.id:
                    for x in range(-8,9):
                        for y in range(-8,9):
                            if abs(x) + abs(y) <= 4:
                                self.game_map[self.game_map.normalize(ship.position + Position(x,y))].is_inspiring += 1
                            if abs(x) + abs(y) <= 8:
                                self.game_map[self.game_map.normalize(ship.position + Position(x, y))].enemy_population_metric += 1.1 ** (-abs(x) - abs(y))
                else:
                    for x in range(-8,9):
                        for y in range(-8,9):
                            if abs(x) + abs(y) <= 8:
                                self.game_map[self.game_map.normalize(ship.position + Position(x, y))].population_metric += 1.1 ** (-abs(x) - abs(y))
            self.game_map[player.shipyard.position].structure = player.shipyard
            for dropoff in player.get_dropoffs():
                self.game_map[dropoff.position].structure = dropoff

        for entity in self.me.get_dropoffs_and_shipyard():
            if self.game_map[entity.position].is_occupied:
                if self.game_map[entity.position].ship.owner != self.me.id:
                    self.game_map[entity.position].mark_safe()
            halite_counter = 0
            for x in range(-8,9):
                for y in range(-8,9):
                    if abs(x) + abs(y) <= 8:
                        halite_counter += self.game_map[self.game_map.normalize(entity.position + Position(x,y))].halite_amount
            entity.surrounding_value = halite_counter

        return turn_start_time

    def update_dictionaries(self, coordinator, logging):
        # for key in self.dict_positions.keys():
        #     if self.game_map[self.dict_positions[key]].ship is None:
        #         logging.info('someone has crashed into me at {}'.format(self.dict_positions[key]))
        #         self.destroyed_by_enemy_count += 1

        for ship in self.me.get_ships():
            if ship.id not in self.still_counts.keys():
                self.still_counts[ship.id] = 0
            if ship.id in self.last_positions.keys():
                if ship.position == self.last_positions[ship.id]:
                    self.still_counts[ship.id] += 1
                else:
                    self.still_counts[ship.id] = 0
            if ship.id in self.game_missions.keys():
                ship.mission = self.game_missions.get(ship.id)

            if ship.id in coordinator.assigned_targets.keys():
                zone = coordinator.assigned_targets[ship.id]
                if zone.halite_per_square >= self.min_halite_to_take \
                        or ship.mission == 'go_to_zone_for_dropoff':
                    ship.coordinator_target_zone = zone
                    zone.update_ships_assigned(ship)
                else:
                    logging.info('dropping zone for ship: {}'.format(ship.id))
                    coordinator.assigned_targets.pop(ship.id, None)
            if ship.id in coordinator.assigned_target_squares.keys():
                if ship.coordinator_target_zone is not None:
                    ship.target_square = coordinator.assigned_target_squares[ship.id]

            if ship.id in self.still_counts.keys():
                ship.still_count = self.still_counts.get(ship.id)

            counter = 0
            if ship.mission == 'go_to_zone':
                for x in range(-3,4):
                    for y in range(-3,4):
                        if abs(x) + abs(y) <= 2:
                            adj_pos = ship.position + Position(x,y)
                            cell = self.game_map[adj_pos]
                            if not cell.is_occupied:
                                if cell.halite_amount >= self.min_halite_to_take * 3:
                                    counter += 3
                                elif cell.halite_amount >= self.min_halite_to_take * 1.5 \
                                        or (cell.is_inspiring >= 2 and cell.halite_amount >= self.min_halite_to_take):
                                    counter += 1
                            # elif cell.fair_game and ship.halite_amount < 300:
                            #     counter += 3
            ship.refresh_mission(self, coordinator, counter)


    @staticmethod
    def end_turn(commands):
        """
        Method to send all commands to the game engine, effectively ending your turn.
        :param commands: Array of commands to send to engine
        :return: nothing.
        """
        send_commands(commands)


def send_commands(commands):
    """
    Sends a list of commands to the engine.
    :param commands: The list of commands to send.
    :return: nothing.
    """
    print(" ".join(commands))
    sys.stdout.flush()
