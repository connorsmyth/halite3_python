import abc

from . import commands, constants
from .positionals import Direction, Position
from .common import read_input
from .pathfinder import Graph
from .test_pathfinder import find_path, create_grid_and_find_path
import logging
from datetime import datetime
import debug_common
import numpy as np
import itertools


class Entity(abc.ABC):
    """
    Base Entity Class from whence Ships, Dropoffs and Shipyards inherit
    """
    def __init__(self, owner, id, position):
        self.owner = owner
        self.id = id
        self.position = position
        self.surrounding_value = -1

    @staticmethod
    def _generate(player_id):
        """
        Method which creates an entity for a specific player given input from the engine.
        :param player_id: The player id for the player who owns this entity
        :return: An instance of Entity along with its id
        """
        ship_id, x_position, y_position = map(int, read_input().split())
        return ship_id, Entity(player_id, ship_id, Position(x_position, y_position))

    def __repr__(self):
        return "{}(id={}, {})".format(self.__class__.__name__,
                                      self.id,
                                      self.position)


class Dropoff(Entity):
    """
    Dropoff class for housing dropoffs
    """
    pass


class Shipyard(Entity):
    """
    Shipyard class to house shipyards
    """
    def __init__(self, owner, id, position):
        super().__init__(owner,id,position)
        self.traffic_jam = False

    # def check_for_traffic_jam(self, game):
    #     search_space = 2
    #     self.traffic_jam = False
    #     count_me = 0
    #     count_enemy = 0
    #     count_empty = 0
    #     x = self.position.x
    #     y = self.position.y
    #     for x_loop in range(x - search_space, x + search_space + 1):
    #         for y_loop in range(y - search_space, y + search_space + 1):
    #             if game.game_map[Position(x_loop, y_loop)].is_occupied:
    #                 if game.game_map[Position(x_loop,y_loop)].ship.owner == game.me.shipyard.owner:
    #                     count_me +=1
    #                 else:
    #                     count_enemy += 1
    #             else:
    #                 count_empty += 1
    #     if count_me > 0.25 * (search_space + 1) ** 2:
    #         self.traffic_jam = True


    def spawn(self):
        """Return a move to spawn a new ship."""
        return commands.GENERATE


class Ship(Entity):
    """
    Ship class to house ship entities
    """
    def __init__(self, owner, id, position, halite_amount):
        super().__init__(owner, id, position)
        self.halite_amount = halite_amount
        self.mission = None
        self.coordinator_target_zone = None
        self.still_count = 0
        self.action = None
        self.target_square = None
        self.best_intention = None
        self.command_sent = False
        # self.had_to_wait = False
        self.enemy_takedown_ship_passive = False
        self.enemy_takedown_ship = False
        self.enemy_inspired = False
        self.enemy_expected_value_if_still = 0
        self.enemy_still_to_gain = 0
        # self.care_for_danger = False

    @property
    def is_full(self):
        """Is this ship at max halite capacity?"""
        return self.halite_amount >= constants.MAX_HALITE

    def make_dropoff(self):
        """Return a move to transform this ship into a dropoff."""
        return "{} {}".format(commands.CONSTRUCT, self.id)

    def move(self, direction):
        """
        Return a move to move this ship in a direction without
        checking for collisions.
        """
        raw_direction = direction
        if not isinstance(direction, str) or direction not in "nsewo":
            raw_direction = Direction.convert(direction)
        return "{} {} {}".format(commands.MOVE, self.id, raw_direction)

    def stay_still(self):
        """
        Don't move this ship.
        """
        return "{} {} {}".format(commands.MOVE, self.id, commands.STAY_STILL)

    @staticmethod
    def _generate(player_id):
        """
        Creates an instance of a ship for a given player given the engine's input.
        :param player_id: The id of the player who owns this ship
        :return: The ship id and ship object
        """
        ship_id, x_position, y_position, halite = map(int, read_input().split())
        return ship_id, Ship(player_id, ship_id, Position(x_position, y_position), halite)

    def __repr__(self):
        return "{}(id={}, {}, cargo={} halite, mission={})".format(self.__class__.__name__,
                                                       self.id,
                                                       self.position,
                                                       self.halite_amount,
                                                       self.mission)

    def __convert_command_to_direction(self, the_command):
        the_direction = Direction.Still
        if the_command == 'w':
            the_direction = Direction.West
        elif the_command == 'n':
            the_direction = Direction.North
        elif the_command == 's':
            the_direction = Direction.South
        elif the_command == 'e':
            the_direction = Direction.East

        return the_direction

    def is_in_zone(self, pos_to_use = None, zone_to_use = None):
        if pos_to_use is None: pos_to_use = self.position
        if zone_to_use is None: zone_to_use = self.coordinator_target_zone
        if zone_to_use != None:
            if (zone_to_use.x_start <= pos_to_use.x) & (zone_to_use.x_end > pos_to_use.x):
                if (zone_to_use.y_start <= pos_to_use.y) & (zone_to_use.y_end > pos_to_use.y):
                    return True
        return False

    def get_target_square(self, game, pos_to_use = None):
        if pos_to_use is None: pos_to_use = self.position
        if self.mission == 'go_to_zone' or self.mission == 'go_to_zone_for_dropoff':
            if self.is_in_zone(pos_to_use) and self.target_square is not None:
                return self.target_square
            else:
                if self.coordinator_target_zone.center in [dropoff.position for dropoff in game.me.get_dropoffs_and_shipyard()]:
                    return self.coordinator_target_zone.center + Position(0,1)
                else:
                    return self.coordinator_target_zone.center
        elif self.mission == 'final_base_return' or self.mission == 'go_to_base':
            closest_base = game.me.shipyard
            for dropoff in game.me.get_dropoffs():
                if game.game_map.calculate_distance(self.position, dropoff.position) < game.game_map.calculate_distance(self.position, closest_base.position):
                    closest_base = dropoff
            return closest_base.position

    def get_adjusted_shipyard_position(self, game_map, shipyard, random):
        if shipyard.traffic_jam \
                and abs(shipyard.position.x - self.position.x) <= 1 \
                and abs(shipyard.position.y - self.position.y) > 0:
            offset_left = shipyard.position + Position(-1,0)
            offset_right = shipyard.position + Position(1,0)
            if game_map.calculate_distance(offset_left, self.position) == game_map.calculate_distance(offset_right, self.position):
                return random.choice([offset_left, offset_right])
            elif game_map.calculate_distance(offset_left, self.position) < game_map.calculate_distance(offset_right, self.position):
                return offset_left
            else:
                return offset_right
        else:
            return shipyard.position

    def special_case_position(self, game, game_map, shipyard, random):

        if shipyard.traffic_jam and \
                (str(shipyard.position) == str(self.position) \
                or str(shipyard.position + Position(0,1)) == str(self.position)
                or str(shipyard.position + Position(0, -1)) == str(self.position)):
            offset_up = self.position + Position(0, -1)
            up_safe = game_map[offset_up].is_empty
            offset_down = self.position + Position(0, 1)
            down_safe = game_map[offset_down].is_empty
            if up_safe and down_safe:
                if game_map.calculate_distance(offset_up, self.coordinator_target_zone.center) == game_map.calculate_distance(offset_down, self.position):
                    return random.choice([offset_up,offset_down])
                elif game_map.calculate_distance(offset_up, self.coordinator_target_zone.center) > game_map.calculate_distance(offset_down, self.position):
                    return offset_down
                else:
                    return  offset_up
            elif up_safe:
                return offset_up
            elif down_safe:
                return offset_down
        elif shipyard.traffic_jam and str(shipyard.position + Position(0,1)) == str(self.position):
            offset_down = self.position + Position(0, 1)
            if game_map[offset_down].is_empty:
                return offset_down
        elif shipyard.traffic_jam and str(shipyard.position + Position(0,2)) == str(self.position):
            target_sq = self.get_target_square(game)
            if target_sq is not None:
                direction = game_map.naive_navigate(self, target_sq, ignore_direction = Direction.North)
                return self.position + Position(direction[0], direction[1])
            else: return self.position + Position(0,1)

        elif shipyard.traffic_jam and str(shipyard.position + Position(0,-2)) == str(self.position):
            target_sq = self.get_target_square(game)
            if target_sq is not None:
                direction = game_map.naive_navigate(self, target_sq, ignore_direction=Direction.South)
                return self.position + Position(direction[0], direction[1])
            else: return self.position + Position(0,-1)

        elif shipyard.traffic_jam and str(shipyard.position + Position(0,-1)) == str(self.position):
            offset_up = self.position + Position(0,-1)
            if game_map[offset_up].is_empty:
                return offset_up
        return None

    def get_ship_direction(self, game, game_map, random, logging):

        possible_directions = []
        afford_to_move = self.halite_amount >= game_map[self.position].halite_amount * 0.1
        special_case_position = self.special_case_position(game, game_map, game.me.shipyard, random)
        if not afford_to_move:
            self.action = 'could not afford to move'
            return self.stay_still(), game_map

        for the_pos, the_dir in self.position.get_surrounding_cardinals_and_directions():
            if game_map[the_pos].is_empty and afford_to_move:
                possible_directions.append(the_dir)

        if self.still_count > 3 and len(possible_directions) > 0:
            single_instruction = self.move(random.choice(possible_directions))
            self.action = 'random, because stayed too still'
            self.still_count = 0

        elif self.mission == 'final_base_return':
            self.action = 'final base return'
            single_instruction = self.move(game_map.naive_navigate(self, game.me.shipyard.position))

        elif self.mission == 'go_to_base':
            self.action = 'going to base'
            adj_shipyard_pos = self.get_adjusted_shipyard_position(game_map, game.me.shipyard, random)
            single_instruction = self.move(game_map.naive_navigate(self,adj_shipyard_pos))

        elif special_case_position is not None:
            self.action = 'going to special case (maybe out of shipyard)'
            single_instruction = self.move(game_map.naive_navigate(self, special_case_position))

        elif self.mission == 'go_to_zone' \
                and self.coordinator_target_zone != None:
            if self.is_in_zone():
                if game_map[self.position].halite_amount >= game.min_halite_to_take:
                    self.action = 'extracting halite from zone'
                    single_instruction = self.stay_still()
                elif self.target_square is not None:
                    self.action = 'in zone, has target square, going for square'
                    single_instruction = self.move(game_map.naive_navigate(self, self.target_square))
                else:
                    self.action = 'in zone, moving to best nearest halite'
                    check_halite = 0
                    pos_to_use = Direction.Still
                    for the_pos in possible_directions:
                        if game_map[self.position + Position(the_pos[0], the_pos[1])].halite_amount >= check_halite:
                            pos_to_use = the_pos
                            check_halite = game_map[self.position + Position(the_pos[0], the_pos[1])].halite_amount
                    single_instruction = self.move(pos_to_use)

            else:
                if game_map[self.position].halite_amount >= game.min_halite_to_take:
                    self.action = 'clearing path to zone'
                    single_instruction = self.stay_still()

                else:
                    self.action = 'going to zone'
                    single_instruction = self.move(game_map.naive_navigate(self,self.coordinator_target_zone.center))

        # elif (game_map[self.position].halite_amount < constants.MAX_HALITE / 10 or self.is_full) \
        #         and len(possible_directions) > 0:
        #     self.action = 'moving randomly'
        #     single_instruction = self.move(random.choice(possible_directions))

        else:
            self.action = 'staying still'
            single_instruction = self.stay_still()
            self.still_count += 1

        direction = self.__convert_command_to_direction(single_instruction.split(' ')[2])
        logging.info('marked positon as safe: {}'.format(self.position))
        game_map[self.position].mark_safe()
        logging.info('marked positon as unsafe: {}'.format(self.position.directional_offset(direction)))
        game_map[self.position.directional_offset(direction)].mark_unsafe(self)
        if self.mission == 'final_base_return':
            game_map[game.me.shipyard.position].mark_safe()
        if str(self.position.directional_offset(direction)) == str(game.me.shipyard.position):
            if self.id not in game.total_halite_for_ship.keys():
                game.total_halite_for_ship[self.id] = 0
            game.total_halite_for_ship[self.id] += self.halite_amount - game_map[self.position].halite_amount / 10

        if single_instruction[-1] == 'o' \
                and (self.mission == 'go_to_base' or (not self.is_in_zone() and self.mission == 'go_to_zone')) \
                and self.action != 'clearing path to zone':
            self.still_count += 1
        if single_instruction[-1] != 'o':
            self.still_count = 0

        return single_instruction, game_map

    # def best_four_moves(self, game, game_map, logging, hurry_up):
    #     arr_dirs = [[Direction.Still, Direction.North, Direction.East],
    #                 [Direction.Still, Direction.North, Direction.West],
    #                 [Direction.Still, Direction.South, Direction.East],
    #                 [Direction.Still, Direction.South, Direction.West]]
    #     if hurry_up:
    #         orig_search_space = 4
    #         search_space = orig_search_space
    #         repeat = 2
    #     else:
    #         orig_search_space = 6
    #         search_space = orig_search_space
    #         repeat = 4
    #
    #     dict_scores = {}
    #     remember_best_halite_score = 0
    #     if self.halite_amount < game_map[self.position].halite_amount * 0.1:
    #         return Direction.Still
    #     if game_map[self.position].is_inspiring >= 2:
    #         if game_map[self.position].halite_amount * 0.75 + self.halite_amount >= 1000:
    #             return Direction.Still
    #     else:
    #         if game_map[self.position].halite_amount * 0.25 + self.halite_amount >= 1000:
    #             return Direction.Still
    #
    #     for core_directions in arr_dirs:
    #
    #         permutations = list(itertools.product(core_directions, repeat = repeat))
    #         for perm in permutations:
    #             perm = tuple(list(perm) + [(0,0), (0,0)])
    #             halite_counter = self.halite_amount
    #             imaginary_pos = Position(self.position.x, self.position.y)
    #             continue_loop = True
    #             arr_all_pos_used = [Position(imaginary_pos.x,imaginary_pos.y)]
    #             for iter in range(search_space):
    #                 if continue_loop:
    #                     afford_to_move = halite_counter >= game_map[imaginary_pos].adjusted_halite_amount * 0.1
    #                     # pos_has_ship = game_map[imaginary_pos].ship is not None
    #
    #                     if perm[iter] == Direction.Still:
    #                         if game_map[imaginary_pos].is_inspiring >= 2:
    #                             halite_counter += game_map[imaginary_pos].adjusted_halite_amount * 0.75
    #                         else:
    #                             halite_counter += game_map[imaginary_pos].adjusted_halite_amount * 0.25
    #                         game_map[imaginary_pos].adjusted_halite_amount = 0.75 * game_map[imaginary_pos].adjusted_halite_amount
    #
    #                     elif not afford_to_move:
    #                         continue_loop = False
    #                     # elif game_map[imaginary_pos].is_dangerous and halite_counter > 500 and iter > 0:
    #                     #     continue_loop = False
    #
    #                     elif game_map[imaginary_pos].ship is not None and imaginary_pos != self.position:
    #                             continue_loop = False
    #                     else:
    #                         imaginary_pos += Position(*perm[iter])
    #                         imaginary_pos = game_map.normalize(imaginary_pos)
    #                         arr_all_pos_used.append(Position(imaginary_pos.x,imaginary_pos.y))
    #                         halite_counter -= game_map[imaginary_pos].adjusted_halite_amount * 0.1
    #                         if imaginary_pos in [entity.position for entity in game.me.get_dropoffs_and_shipyard()]:
    #                             continue_loop = False
    #                     # if (len(game.players) == 2 or game.turn_number > 300) and game_map[imaginary_pos].fair_game and self.halite_amount < 300:
    #                     #     halite_counter += 1000
    #
    #                     if halite_counter >= 1000:
    #                         if iter + 1 < search_space:
    #                             search_space = iter + 1
    #                             remember_best_halite_score = halite_counter
    #                         else:
    #                             remember_best_halite_score = max(halite_counter,remember_best_halite_score)
    #                         dict_scores[perm[:search_space]] = halite_counter - self.halite_amount
    #                         continue_loop = False
    #             if continue_loop:
    #                 dict_scores[perm[:search_space]] = halite_counter - self.halite_amount
    #                 remember_best_halite_score = max(halite_counter, remember_best_halite_score)
    #             game_map.reset_adjusted_halite_amount(arr_all_pos_used)
    #
    #     dict_scores = {key: dict_scores[key] for key in dict_scores.keys() if len(key) == search_space}
    #     list_best_directions = sorted(dict_scores, key=dict_scores.get, reverse=True)
    #     if search_space == orig_search_space and dict_scores[list_best_directions[0]] < game.average_halite * 0.25 * 3:
    #         logging.info('nothing close is good')
    #     logging.info('best_directions: {}'.format(list_best_directions[:min(len(list_best_directions),2)]))
    #     logging.info(remember_best_halite_score)
    #     logging.info(remember_best_halite_score - self.halite_amount)
    #     ordered_top_dirs = []
    #     for item in list_best_directions:
    #         if item[0] not in ordered_top_dirs:
    #             ordered_top_dirs.append(item[0])
    #         if len(ordered_top_dirs) == 2:
    #             break
    #     if len(ordered_top_dirs) == 1:
    #         return ordered_top_dirs[0]
    #     else:
    #         return ordered_top_dirs

    def best_four_moves_enemy(self, game, game_map):
        arr_dirs = [[Direction.Still, Direction.North, Direction.East],
                    [Direction.Still, Direction.North, Direction.West],
                    [Direction.Still, Direction.South, Direction.East],
                    [Direction.Still, Direction.South, Direction.West]]

        orig_search_space = 4
        search_space = orig_search_space
        repeat = orig_search_space - 2

        dict_scores = {}
        dict_final_positions = {}
        remember_best_halite_score = 0
        if self.halite_amount < game_map[self.position].halite_amount * 0.1:
            return Direction.Still
        if game_map[self.position].halite_amount * 0.25 + self.halite_amount >= 1000:
            return Direction.Still
        for core_directions in arr_dirs:
            permutations = list(itertools.product(core_directions, repeat = repeat))
            for perm in permutations:
                perm = tuple(list(perm) + [(0,0), (0,0)])
                halite_counter = self.halite_amount
                imaginary_pos = Position(self.position.x, self.position.y)
                continue_loop = True
                arr_all_pos_used = [Position(imaginary_pos.x,imaginary_pos.y)]
                for iter in range(search_space):
                    if continue_loop:
                        mapcell = game_map[imaginary_pos]
                        afford_to_move = halite_counter >= mapcell.adjusted_halite_amount * 0.1

                        if perm[iter] == Direction.Still:
                            halite_counter += mapcell.adjusted_halite_amount * 0.25
                            mapcell.adjusted_halite_amount = 0.75 * mapcell.adjusted_halite_amount
                            # if mapcell.is_inspiring >= 2:
                            #     halite_counter += mapcell.adjusted_halite_amount * 0.75
                            # else:
                            #     halite_counter += mapcell.adjusted_halite_amount * 0.25
                            # mapcell.adjusted_halite_amount = 0.75 * mapcell.adjusted_halite_amount

                        elif not afford_to_move:
                            continue_loop = False
                            break

                        else:
                            imaginary_pos += Position(*perm[iter])
                            imaginary_pos = game_map.normalize(imaginary_pos)
                            mapcell = game_map[imaginary_pos]
                            arr_all_pos_used.append(Position(imaginary_pos.x,imaginary_pos.y))
                            halite_counter -= mapcell.adjusted_halite_amount * 0.1
                        if mapcell.ship is not None and imaginary_pos != self.position:
                            continue_loop = False
                            break
                        if halite_counter >= 1000:
                            if iter + 1 < search_space:
                                search_space = iter + 1
                                remember_best_halite_score = halite_counter
                                dict_final_positions = {perm[:search_space] : Position(imaginary_pos.x, imaginary_pos.y)}
                            else:
                                remember_best_halite_score = max(halite_counter,remember_best_halite_score)
                                dict_final_positions[perm[:search_space]] = Position(imaginary_pos.x, imaginary_pos.y)
                            dict_scores[perm[:search_space]] = halite_counter - self.halite_amount
                            continue_loop = False
                if continue_loop:
                    dict_scores[perm[:search_space]] = halite_counter - self.halite_amount
                    remember_best_halite_score = max(halite_counter, remember_best_halite_score)
                game_map.reset_adjusted_halite_amount(arr_all_pos_used)
        dict_scores = {key: dict_scores[key] for key in dict_scores.keys() if len(key) == search_space}
        list_best_directions = sorted(dict_scores, key=dict_scores.get, reverse=True)
        # return list_best_directions[0][0]
        ordered_top_dirs = []
        for item in list_best_directions:
            if item[0] not in ordered_top_dirs:
                ordered_top_dirs.append(item[0])
            if len(ordered_top_dirs) == 2:
                break
        if len(ordered_top_dirs) == 1:
            return ordered_top_dirs[0]
        else:
            return ordered_top_dirs

    def best_four_moves_v2(self, game, game_map, logging, hurry_up):
        arr_dirs = [[Direction.Still, Direction.North, Direction.East],
                    [Direction.Still, Direction.North, Direction.West],
                    [Direction.Still, Direction.South, Direction.East],
                    [Direction.Still, Direction.South, Direction.West]]
        if hurry_up:
            orig_search_space = 4
            search_space = orig_search_space
            repeat = orig_search_space - 2
        else:
            orig_search_space = 6
            search_space = orig_search_space
            repeat = orig_search_space - 2

        dict_scores = {}
        dict_final_positions = {}
        remember_best_halite_score = 0
        if self.halite_amount < game_map[self.position].halite_amount * 0.1:
            return Direction.Still
        if game_map[self.position].is_inspiring >= 2:
            if game_map[self.position].halite_amount * 0.75 + self.halite_amount >= 1000:
                return Direction.Still
        else:
            if game_map[self.position].halite_amount * 0.25 + self.halite_amount >= 1000:
                return Direction.Still

        for core_directions in arr_dirs:
            permutations = list(itertools.product(core_directions, repeat = repeat))
            for perm in permutations:
                perm = tuple(list(perm) + [(0,0), (0,0)])
                halite_counter = self.halite_amount
                imaginary_pos = Position(self.position.x, self.position.y)
                continue_loop = True
                arr_all_pos_used = [Position(imaginary_pos.x,imaginary_pos.y)]
                for iter in range(search_space):
                    if continue_loop:
                        mapcell = game_map[imaginary_pos]
                        afford_to_move = halite_counter >= mapcell.adjusted_halite_amount * 0.1

                        if perm[iter] == Direction.Still:
                            if mapcell.is_inspiring >= 2:
                                halite_counter += mapcell.adjusted_halite_amount * 0.75
                            else:
                                halite_counter += mapcell.adjusted_halite_amount * 0.25
                                mapcell.adjusted_halite_amount = 0.75 * mapcell.adjusted_halite_amount

                        elif not afford_to_move:
                            continue_loop = False
                            break

                        else:
                            imaginary_pos += Position(*perm[iter])
                            imaginary_pos = game_map.normalize(imaginary_pos)
                            mapcell = game_map[imaginary_pos]
                            arr_all_pos_used.append(Position(imaginary_pos.x,imaginary_pos.y))
                            halite_counter -= mapcell.adjusted_halite_amount * 0.1
                            if imaginary_pos in [entity.position for entity in game.me.get_dropoffs_and_shipyard()]:
                                continue_loop = False
                                break
                            if mapcell.two_p_dangerous and halite_counter > 500 and iter > 0:
                                continue_loop = False
                                break
                        if mapcell.is_occupied:
                            if mapcell.ship.owner != game.me.id:
                                if mapcell.ship.enemy_takedown_ship and halite_counter < 300:
                                    halite_counter += 500

                        if mapcell.is_occupied and imaginary_pos != self.position:
                            if mapcell.ship.owner == game.me.id and iter < 1:
                                if mapcell.ship.halite_amount < 700:
                                    continue_loop = False
                                    break
                        if game_map[imaginary_pos].enemy_intention and iter == 0:
                            if game.still_counts.get(self.id) is None:
                                continue_loop = False
                                break
                            elif game.still_counts[self.id] < 6:
                                continue_loop = False
                                break
                        if halite_counter >= 1000:
                            if iter + 1 < search_space:
                                search_space = iter + 1
                                remember_best_halite_score = halite_counter
                                dict_final_positions = {perm[:search_space] : Position(imaginary_pos.x, imaginary_pos.y)}
                            else:
                                remember_best_halite_score = max(halite_counter,remember_best_halite_score)
                                dict_final_positions[perm[:search_space]] = Position(imaginary_pos.x, imaginary_pos.y)
                            dict_scores[perm[:search_space]] = halite_counter - self.halite_amount
                            continue_loop = False
                if continue_loop:
                    dict_scores[perm[:search_space]] = halite_counter - self.halite_amount
                    remember_best_halite_score = max(halite_counter, remember_best_halite_score)
                game_map.reset_adjusted_halite_amount(arr_all_pos_used)

        dict_scores = {key: dict_scores[key] for key in dict_scores.keys() if len(key) == search_space}
        list_best_directions = sorted(dict_scores, key=dict_scores.get, reverse=True)

        if search_space < orig_search_space:
            list_best_directions = self.choose_path_with_shortest_dist_home(game, game_map, dict_final_positions)

        logging.info('best_directions: {}'.format(list_best_directions[:min(len(list_best_directions),2)]))
        ordered_top_dirs = []
        for item in list_best_directions:
            if item[0] not in ordered_top_dirs:
                ordered_top_dirs.append(item[0])
            if len(ordered_top_dirs) == 2:
                break
        if len(ordered_top_dirs) == 1:
            return ordered_top_dirs[0]
        else:
            return ordered_top_dirs

    def choose_path_with_shortest_dist_home(self, game, game_map, dict_final_positions):
        unique_end_positions = list(set(dict_final_positions.values()))
        pos = unique_end_positions[0]
        closest_dropoff = game.me.shipyard
        closest_dist = game_map.calculate_distance(pos, closest_dropoff.position)
        for entity in game.me.get_dropoffs():
            if game_map.calculate_distance(pos, entity.position) < closest_dist:
                closest_dist = game_map.calculate_distance(pos, entity.position)
                closest_dropoff = entity
        dict_distances = {key: game_map.calculate_distance(dict_final_positions[key], closest_dropoff.position) for key in dict_final_positions.keys()}
        list_best_directions = sorted(dict_distances, key=dict_distances.get, reverse=False)
        return list_best_directions

    def get_best_intention(self, game, game_map, logging, coordinator, command_queue, turn_start_time):

        afford_to_move = self.halite_amount >= game_map[self.position].halite_amount * 0.1

        if coordinator.next_dropoff_zone is not None:
            if 4000 <= game.me.halite_amount + game_map[self.position].halite_amount + self.halite_amount \
                    and not game_map[self.position].has_structure \
                    and self.target_square is not None:
                if self.position == self.target_square:
                    command_queue.append(self.make_dropoff())
                    self.command_sent = True
                    coordinator.last_dropoff_turn = game.turn_number
                    coordinator.reset_dropoff_instructions()
                    return

            if game.me.halite_amount + game_map[self.position].halite_amount + self.halite_amount > coordinator.adjust_halite_in_bank \
                    and not game_map[self.position].has_structure \
                    and game.still_counts.get(self.id) is not None \
                    and game_map.calculate_distance(self.position, coordinator.next_dropoff_zone.center) < 3:
                    # and coordinator.next_dropoff_zone == self.coordinator_target_zone \
                    # and self.is_in_zone():
                if game.still_counts[self.id] > 2:
                    command_queue.append(self.make_dropoff())
                    self.command_sent = True
                    coordinator.last_dropoff_turn = game.turn_number
                    coordinator.reset_dropoff_instructions()
                    return

        if not afford_to_move:
            self.best_intention = Direction.Still
            return
        if game_map[self.position].is_inspiring >= 2:
            halite_for_cell = 3 * game_map[self.position].halite_amount * 0.25
        else:
            halite_for_cell = game_map[self.position].halite_amount * 0.25
        if self.mission != 'final_base_return' \
                and self.mission != 'go_to_base' \
                and self.mission != 'collect_from_zone' \
                and halite_for_cell / 0.25 >= 2 * game.min_halite_to_take \
                and halite_for_cell + self.halite_amount <= 1000:
            self.best_intention = Direction.Still
            return
        # if (self.mission == 'go_to_base' or self.mission == 'collect_from_zone') \
        if (self.mission == 'go_to_base') \
                and halite_for_cell + self.halite_amount <= 1000 \
                and halite_for_cell / 0.25 >= 2 * game.average_halite:
            self.best_intention = Direction.Still
            return
        hurry_up = False
        if not debug_common.debug_mode and (datetime.now() - turn_start_time).total_seconds() > 1.3:
            hurry_up = True
            logging.info('hurried up')
        if self.mission == 'collect_from_zone':
            self.best_intention = self.best_four_moves_v2(game, game_map, logging, hurry_up)
        else:
            target_square = self.get_target_square(game)
            if target_square is None:
                self.command_sent = True
                return
            self.best_intention = self.best_moves_to_base(game, game_map, target_square, hurry_up)
            # self.best_intention = game_map.planned_navigate(self, target_square, best_intention=True)

    def best_moves_to_base(self, game, game_map, target_square, hurry_up, ignore_friendly=True):
        general_directions = game_map.get_unsafe_moves(self.position, target_square)
        if hurry_up:
            max_search_space = 4
        else:
            max_search_space = 5

        all_arr = []
        for dir in general_directions:
            if dir == Direction.North:
                all_arr.append([Direction.North, Direction.East])
                all_arr.append([Direction.North, Direction.West])

            elif dir == Direction.South:
                all_arr.append([Direction.South, Direction.East])
                all_arr.append([Direction.South, Direction.West])

            elif dir == Direction.East:
                all_arr.append([Direction.North, Direction.East])
                all_arr.append([Direction.South, Direction.East])

            elif dir == Direction.West:
                all_arr.append([Direction.North, Direction.West])
                all_arr.append([Direction.South, Direction.West])


        my_arr = []
        for item in all_arr:
            if item not in my_arr:
                my_arr.append(item)

        dict_final_pos = {}
        dict_final_score = {}
        dict_final_pos_incl_same_team = {}
        dict_final_score_incl_same_team = {}
        search_space = min(game_map.calculate_distance(self.position, target_square), max_search_space)
        for gen_dir in my_arr:
            permutations = list(itertools.product(gen_dir, repeat=search_space))
            for perm in permutations:
                # looking to minimise score
                score = 0
                imaginary_pos = Position(self.position.x, self.position.y)
                continue_loop = True
                can_include_as_primary = True
                for iter in range(search_space):
                    if continue_loop:
                        imaginary_pos = game_map.normalize(imaginary_pos + Position(*perm[iter]))
                        mapcell = game_map[imaginary_pos]
                        if mapcell.enemy_intention and iter == 0:
                            continue_loop = False
                            break
                        if mapcell.is_occupied \
                                or (mapcell.enemy_passive_takedown and self.halite_amount < 300):
                            if mapcell.ship.owner != game.me.id:
                                continue_loop = False
                                break
                            # if mapcell.ship.owner == game.me.id:
                            #     can_include_as_primary = False
                        if mapcell.two_p_dangerous:
                            score += 400
                        score += mapcell.halite_amount
                if continue_loop:
                    if can_include_as_primary:
                        dict_final_pos[perm] = game_map.calculate_distance(imaginary_pos, target_square)
                        dict_final_score[perm] = score
                    else:
                        dict_final_pos_incl_same_team[perm] = game_map.calculate_distance(imaginary_pos, target_square)
                        dict_final_score_incl_same_team[perm] = score

        dict_final_pos = {key:dict_final_pos[key] for key in dict_final_pos if dict_final_pos[key] <= min(dict_final_pos.values())}
        dict_final_score = {key:dict_final_score[key] for key in dict_final_pos}
        list_best_directions = sorted(dict_final_score, key=dict_final_score.get, reverse=False)
        ordered_top_dirs = []

        if len(list_best_directions) == 0:
            return Direction.Still
        for item in list_best_directions:
            if item[0] not in ordered_top_dirs:
                ordered_top_dirs.append(item[0])
            if len(ordered_top_dirs) == 2:
                break
        if len(ordered_top_dirs) == 1:
            return ordered_top_dirs[0]
        else:
            return ordered_top_dirs


    def get_intention(self, attempt_no = None):
        if type(self.best_intention) is list:
            if attempt_no == None: attempt_no = 1
            if attempt_no // 5 == attempt_no / 5:
                intention = self.best_intention[1]
            else:
                intention = self.best_intention[0]
        else:
            intention = self.best_intention
        return intention

    def best_intention_pos(self, attempt_no = None):
        intention = self.get_intention(attempt_no)
        return Position(intention[0], intention[1])

    def resolve_intention(self, game, game_map, attempt_no):
        intention = self.get_intention(attempt_no)
        home_positions = [item.position for item in game.me.get_dropoffs() + [game.me.shipyard]]

        normalised_pos = game_map.normalize(self.position + self.best_intention_pos(attempt_no))
        occupied_by_enemy = False
        if game_map[normalised_pos].is_occupied:
            if game_map[normalised_pos].ship.owner != game.me.id:
                occupied_by_enemy = True

        if not game_map[normalised_pos].is_occupied \
                and not game_map[normalised_pos].enemy_intention:
            self.command_sent = True
            game_map[self.position].mark_safe()
            game_map[normalised_pos].mark_unsafe(self)
            return self.move(intention)

        elif occupied_by_enemy \
                and game_map[normalised_pos].enemy_passive_takedown:
            logging.info('passively collided with ship')
            logging.info(self.position)
            self.command_sent = True
            game_map[self.position].mark_safe()
            game_map[normalised_pos].mark_unsafe(self)
            return self.move(intention)

        elif game_map[normalised_pos].enemy_intention \
                and not game_map[normalised_pos].is_occupied:
            if game.still_counts.get(self.id) is not None:
                if game.still_counts[self.id] > 6:
                    logging.info('decided to go as still for too long')
                    self.command_sent = True
                    game_map[self.position].mark_safe()
                    game_map[normalised_pos].mark_unsafe(self)
                    return self.move(intention)

        elif self.mission == 'final_base_return' and normalised_pos in home_positions:
            self.command_sent = True
            game_map[self.position].mark_safe()
            return self.move(intention)

        elif intention == Direction.Still:
            self.command_sent = True
            return self.stay_still()

        elif occupied_by_enemy and len(game.players) == 2:
            if game_map[normalised_pos].ship.enemy_takedown_ship:
                self.command_sent = True
                game_map[self.position].mark_safe()
                game_map[normalised_pos].mark_unsafe(self)
                return self.move(intention)

    def refresh_mission(self, game, coordinator, counter):
        if self.mission == None:
            self.mission = ''

        if game.turn_number > constants.MAX_TURNS - game.game_map.width / 1.8:
            self.mission = 'final_base_return'
            return

        if self.mission == 'go_to_zone_for_dropoff' and coordinator.next_dropoff_zone is None:
            self.mission = 'go_to_zone'

        if self.mission == 'go_to_zone_for_dropoff':
            return

        if self.mission == 'go_to_zone' and counter > 2:
            logging.info('changing to collect from zone early for ship {}'.format(self.id))
            self.mission = 'collect_from_zone'
            self.coordinator_target_zone = coordinator.arr_zones[int(self.position.y / game.window_size)][int(self.position.x / game.window_size)]

        if self.mission == 'go_to_zone' and (self.is_in_zone() or counter > 2):
            # if counter > 2:
            #     logging.info('changing to collect from zone early for ship {}'.format(self.id))
            self.mission = 'collect_from_zone'

        if self.mission == 'collect_from_zone' and game.still_counts.get(self.id) is not None:
            if game.still_counts[self.id] >= 20:
                self.mission = 'go_to_base'

        home_positions = [item.position for item in game.me.get_dropoffs() + [game.me.shipyard]]
        if self.position in home_positions or self.mission == '':
            self.mission = 'go_to_zone'
            self.coordinator_target_zone = None

        # if self.mission == 'collect_from_zone':
        #     zone = self.coordinator_target_zone
        #     if zone.distance_from_zone_min(self.position, game.game_map) < 15:
        #         self.mission = 'go_to_zone'

        if (self.mission == 'go_to_base') and (self.halite_amount >= constants.MAX_HALITE * 0.2):
            return

        if (self.halite_amount >= constants.MAX_HALITE * 1):
            self.mission = 'go_to_base'
            return

        # if game.game_map[self.position].is_dangerous \
        #         and game.destroyed_by_enemy_count > 5 \
        #         and self.halite_amount >= max(constants.MAX_HALITE - (game.destroyed_by_enemy_count - 5) * 40, 600):
        #     self.mission = 'go_to_base'
        #     logging.info('going to base early as in dangerous place: ship id {}'.format(self.id))

        return

class Zone:

    def distance_from_point(self, target_pos, game_map):
        return game_map.calculate_distance(self.center, target_pos)

    def total_number_of_squares(self):
        count = 0
        for x in range(self.x_start, self.x_end):
            for y in range(self.y_start, self.y_end):
                count += 1
        return count

    def get_position_of_highest_theoretical(self, game_map):
        highest_halite_pos = Position(self.x_start, self.y_start)
        highest_halite = game_map[highest_halite_pos].adjusted_halite_amount
        for x in range(self.x_start, self.x_end):
            for y in range(self.y_start, self.y_end):
                if highest_halite < game_map[Position(x,y)].adjusted_halite_amount:
                    highest_halite = game_map[Position(x,y)].adjusted_halite_amount
                    highest_halite_pos = Position(x,y)
        return highest_halite_pos

    def update_collective_halite(self, loop_dropoff_col_halite, collective_halite, arr_top, collective_population_metric, counter_inspired, enemy_collective_population_metric):
        self.collective_halite = collective_halite
        self.dropoff_accounting_of_halite = loop_dropoff_col_halite
        self.collective_population_metric = collective_population_metric
        self.enemy_collective_population_metric = enemy_collective_population_metric
        self.halite_per_square = self.collective_halite / self.sq_count
        self.value_for_new_ship = self.collective_halite
        self.top_pos_1 = arr_top[0][0]
        self.top_pos_2 = arr_top[1][0]
        self.top_pos_3 = arr_top[2][0]
        self.top_pos_4 = arr_top[3][0]
        self.top_pos_5 = arr_top[4][0]
        self.top_pos_arr = [arr_top[i][0] for i in range(len(arr_top))]
        self.counter_inspired = counter_inspired
        self.inspired_collective_halite = self.collective_halite if self.counter_inspired <= 3 else self.collective_halite * 3
        self.inspired_value_for_new_ship = self.inspired_collective_halite

    def assign_closest_ship_to_zone(self, game):
        for ship in game.me.get_ships():
            if ship.mission == 'go_to_zone_for_dropoff':
                ship.coordinator_target_zone = self
                return
        closest_ship = None
        dist_closest = 10000
        target = self.center
        for ship in game.me.get_ships():
            dist = game.game_map.calculate_distance(ship.position, target)
            if dist < dist_closest:
                dist_closest = dist
                closest_ship = ship
        if closest_ship is not None:
            closest_ship.mission = 'go_to_zone_for_dropoff'
            closest_ship.coordinator_target_zone = self
            closest_ship.target_square = self.top_pos_1
            logging.info('assigning ship: {} to target_zone: {} for a dropoff'.format(closest_ship.id, self))

    def refresh_values(self, game):
        self.ships_assigned_to_zone = []
        game_map = game.game_map
        final_zone_mark_width = (game_map.width // game.window_size) * game.window_size
        final_zone_mark_height = (game_map.height // game.window_size) * game.window_size
        if self.x_end == final_zone_mark_width:
            self.x_end = game_map.width
        if self.y_end == final_zone_mark_height:
            self.y_end = game_map.height
        loop_col_halite = 0
        loop_dropoff_col_halite = 0
        collective_population_metric = 0
        counter_inspired = 0
        enemy_collective_population_metric = 0

        pos_1 = [None, 0]
        pos_2 = [None, 0]
        pos_3 = [None, 0]
        pos_4 = [None, 0]
        pos_5 = [None, 0]
        for x in range(self.x_start, self.x_end):
            for y in range(self.y_start, self.y_end):
                counter_inspired += 1 if game_map[Position(x, y)].is_inspiring >= 2 else 0
                cell = game_map[Position(x, y)]
                loop_col_halite += cell.halite_amount
                loop_dropoff_col_halite += cell.halite_to_count_for_new_dropoffs
                collective_population_metric += cell.population_metric
                enemy_collective_population_metric += cell.enemy_population_metric
                if cell.halite_amount > pos_5[1]:
                    pos_5[0] = Position(x,y)
                    pos_5[1] = game_map[pos_5[0]].halite_amount
                if pos_5[1] > pos_4[1]:
                    pos_tmp = pos_5
                    pos_5 = pos_4
                    pos_4 = pos_tmp
                if pos_4[1] > pos_3[1]:
                    pos_tmp = pos_4
                    pos_4 = pos_3
                    pos_3 = pos_tmp
                if pos_3[1] > pos_2[1]:
                    pos_tmp = pos_3
                    pos_3 = pos_2
                    pos_2 = pos_tmp
                if pos_2[1] > pos_1[1]:
                    pos_tmp = pos_2
                    pos_2 = pos_1
                    pos_1 = pos_tmp
        self.update_collective_halite(loop_dropoff_col_halite, loop_col_halite, [pos_1, pos_2, pos_3, pos_4, pos_5], collective_population_metric, counter_inspired, enemy_collective_population_metric)

    def get_center(self):
        return Position(int(self.x_start / 2 + self.x_end / 2), int(self.y_start / 2 + self.y_end / 2))

    def __init__(self, game, x_start, x_end, y_start, y_end):
        self.ships_assigned_to_zone = []
        self.turn_number_last_update = 0
        self.x_start = x_start
        self.x_end = x_end
        self.y_start = y_start
        self.y_end = y_end
        self.center = Position(int(self.x_start / 2 + self.x_end / 2), int(self.y_start / 2 + self.y_end / 2))
        self.distance_from_shipyard = self.distance_from_point(game.me.shipyard.position, game.game_map)
        self.distance_from_enemy = min([self.distance_from_point(game.players[player].shipyard.position, game.game_map) for player in game.players if player != game.my_id])
        self.closer_to_home = self.distance_from_shipyard * 0.1 <= self.distance_from_enemy
        self.sq_count = self.total_number_of_squares()
        self.refresh_values(game)

    def update_ships_assigned(self, ship):
        self.ships_assigned_to_zone.append(ship)
        self.value_for_new_ship = self.collective_halite * (0.9 ** len(self.ships_assigned_to_zone))
        self.inspired_value_for_new_ship = self.inspired_collective_halite * (0.9 ** len(self.ships_assigned_to_zone))
        return self

    def assign_position(self, ship, game_map):
        for position in [self.top_pos_1, self.top_pos_2, self.top_pos_3, self.top_pos_4, self.top_pos_5]:
            if position is not None and ship.target_square is None:
                if not game_map[position].is_targeted():
                    game_map[position].mark_target(ship)
                    ship.target_square = position

    def __repr__(self):
        return 'Zone(collective_halite: {}, x_start: {}, x_end: {}, y_start: {}, y_end: {}, dist_from_shipyard: {}, toppos 1,2,3: {}, {}, {})'.format(self.collective_halite, self.x_start, self.x_end, self.y_start, self.y_end, self.distance_from_shipyard, self.top_pos_1, self.top_pos_2, self.top_pos_3)

class cluster:
    def __init__(self, center_zone):
        self.num_surrounding = 13
        self.center_zone = center_zone
        self.dist_from_nearest_dropoff = min([])
        self.dict_zones

class Coordinator:

    def __init__(self, game):
        game_map = game.game_map
        self.plan = None
        self.instructions = {}
        self.zones = {}
        self.assigned_targets = {}
        self.ship_value = 0
        self.zones_weighed = False

        self.influence_target_pos = Position(0,0)
        self.next_dropoff_zone = None
        self.influence_number_of_ships = 0
        self.adjust_halite_in_bank = 0
        self.dropoff_thresholds = DropoffThresholds(game)

        self.last_dropoff_turn = 0

    def weigh_zones(self, game):
        game_map = game.game_map
        self.total_zones = game_map.height * game_map.width / (game.window_size**2)

        mat = []
        for iter in list(range(game_map.width // game.window_size)):
            mat.append(list(range(game_map.width // game.window_size)))
        self.arr_zones = mat

        final_zone_mark_width = (game_map.width // game.window_size) * game.window_size
        final_zone_mark_height = (game_map.height // game.window_size) * game.window_size
        for zone_x in range(0, game_map.width // game.window_size):
            for zone_y in range(0, game_map.height // game.window_size):
                x_start = zone_x * game.window_size
                y_start = zone_y * game.window_size
                x_end = x_start + game.window_size
                y_end = y_start + game.window_size
                if x_end == final_zone_mark_width:
                    x_end = game_map.width
                if y_end == final_zone_mark_height:
                    y_end = game_map.height
                zone = Zone(game, x_start, x_end, y_start, y_end)
                self.zones['{},{}'.format(zone_x, zone_y)] = zone
                self.arr_zones[int(zone_y)][int(zone_x)] = zone
        self.zones_weighed = True

    def generate_game_plan(self, game, logging):

        if game.turn_number < 40 or game.turn_number > 350:
            halite_multiplier = 0.4
            halite_multiplier = 0.8
        else:
            # halite_multiplier = 0.8
            halite_multiplier = 1.1

        game.average_halite = game.game_map.get_total_halite() * halite_multiplier / game.game_map.width / game.game_map.height
        game.min_halite_to_take = game.average_halite * halite_multiplier
        self.ship_value = 1000

        if not self.zones_weighed:
            self.weigh_zones(game)

        count_assigned = 0
        if game.game_map.width >= 56 or len(game.players) == 4:
            distance_weight_multiplier = 1.12
        else:
            distance_weight_multiplier = 1.12 - (0.04 * game.turn_number / constants.MAX_TURNS)

        dict_sur_val = {entity.id: entity.surrounding_value for entity in game.me.get_dropoffs()}
        best_dropoff_potential = 0
        if len(dict_sur_val) > 0:
            logging.info('sur_val for turn number {}'.format(game.turn_number))
            logging.info(dict_sur_val)
            best_entity_id = sorted(dict_sur_val, key = dict_sur_val.get, reverse = True)[0]
            best_dropoff_potential = dict_sur_val[best_entity_id]

        for ship in game.me.get_ships():
            if ship.coordinator_target_zone is None:

                if ship.position == game.me.shipyard.position and self.influence_target_pos != Position(0,0):
                    influenced_position = self.influence_target_pos
                    bool_position_was_influenced = True
                elif ship.position == game.me.shipyard.position and self.influence_target_pos == Position(0,0) \
                        and game.me.shipyard.surrounding_value * 3 < best_dropoff_potential:
                    influenced_position = game.me.get_dropoff(best_entity_id).position
                    logging.info('redirected from shipyard because no halite around there')
                    bool_position_was_influenced = False
                else:
                    influenced_position = ship.position
                    bool_position_was_influenced = False

                if len(game.players) == 2:
                    dict_halite_zones = {key: self.zones[key].value_for_new_ship * (distance_weight_multiplier ** (50 - game.game_map.calculate_distance(influenced_position, self.zones[key].center)) + 1)
                                         for key in self.zones
                                         if self.zones[key].closer_to_home}
                else:
                    dict_halite_zones = {key: self.zones[key].inspired_value_for_new_ship * (distance_weight_multiplier ** (50 - game.game_map.calculate_distance(influenced_position, self.zones[key].center)) + 1)
                                         for key in self.zones
                                         if self.zones[key].closer_to_home}


                list_halite_zones = sorted(dict_halite_zones, key=dict_halite_zones.get, reverse=True)
                for zone_num in list_halite_zones:
                    zone = self.zones[zone_num]
                    if zone.halite_per_square > game.min_halite_to_take:
                        zone.update_ships_assigned(ship)
                        self.assigned_targets[ship.id] = zone
                        ship.coordinator_target_zone = zone
                        count_assigned += 1
                        if bool_position_was_influenced:
                            if self.influence_number_of_ships <= 1 and self.influence_target_pos != Position(0, 0):
                                self.influence_target_pos = Position(0, 0)
                            if self.influence_number_of_ships > 0:
                                self.influence_number_of_ships -= 1
                        break
    def check_generate_new_ship(self, game, command_queue):
        game_map = game.game_map
        me = game.me
        ship_count = len(me.get_ships())

        if constants.MAX_TURNS - game.turn_number > 110 \
                and 'c' not in " ".join(command_queue) \
                and me.halite_amount - self.adjust_halite_in_bank >= constants.SHIP_COST \
                and not game_map[game.me.shipyard].is_occupied \
                and game_map.get_total_halite() / max(ship_count, 1) > (self.dropoff_thresholds.variable_ship_cutoff - (len(game.me.get_dropoffs()) * 400) + (game.turn_number * 5)):
            command_queue.append(me.shipyard.spawn())

        # if len(game.players) == 4:
        #     if 1000 < game_map.get_total_halite() / (sum([len(player.get_ships()) for player in game.players.values()]) + 1) \
        #             and not game_map[me.shipyard].is_occupied \
        #             and 'c' not in " ".join(command_queue) \
        #             and me.halite_amount - self.adjust_halite_in_bank >= constants.SHIP_COST:
        #         command_queue.append(me.shipyard.spawn())
        return

    def check_map_averages(self, game, logging):
        cluster_arr = []
        orig_cluster_arr = []
        col_halite = []
        ave_halite = []
        zone_has_shipyard_override = []
        pop_averages = []
        enemy_pop_averages = []
        arr_centers = []
        individual_arr = []

        # inspiring = []

        for iter in list(range(int(game.game_map.height / game.window_size))):
            cluster_arr.append(list(range(int(game.game_map.height / game.window_size))))
            orig_cluster_arr.append(list(range(int(game.game_map.height / game.window_size))))
            col_halite.append(list(range(int(game.game_map.height / game.window_size))))
            ave_halite.append(list(range(int(game.game_map.height / game.window_size))))
            zone_has_shipyard_override.append(list(range(int(game.game_map.height / game.window_size))))
            pop_averages.append(list(range(int(game.game_map.height / game.window_size))))
            arr_centers.append(list(range(int(game.game_map.height / game.window_size))))
            enemy_pop_averages.append(list(range(int(game.game_map.height / game.window_size))))
            individual_arr.append(list(range(int(game.game_map.height / game.window_size))))
            
            # inspiring.append(list(range(int(game.game_map.height / game.window_size))))

        for row in range(len(cluster_arr)):
            for col in range(len(cluster_arr)):
                weighed_halite = 0
                orig_weighed_halite = 0
                population_score = 0
                for row_adj in range(-2, 3):
                    for col_adj in range(-2, 3):
                        if abs(row_adj) + abs(col_adj) <= 2:
                            get_row = int((row + row_adj) % (game.game_map.height / game.window_size))
                            get_col = int((col + col_adj) % (game.game_map.width / game.window_size))
                            # weighed_halite += (2 ** -(abs(row_adj) + abs(col_adj))) * self.arr_zones[get_row][get_col].collective_halite
                            orig_weighed_halite += (3 ** -(abs(row_adj) + abs(col_adj))) * self.arr_zones[get_row][get_col].collective_halite
                            weighed_halite += (3 ** -(abs(row_adj) + abs(col_adj))) * self.arr_zones[get_row][get_col].dropoff_accounting_of_halite
                cluster_arr[row][col] = int(weighed_halite)
                orig_cluster_arr[row][col] = int(orig_weighed_halite)
                individual_arr[row][col] = self.arr_zones[get_row][get_col].dropoff_accounting_of_halite
                col_halite[row][col] = self.arr_zones[row][col].collective_halite
                ave_halite[row][col] = int(col_halite[row][col] / self.arr_zones[row][col].total_number_of_squares())
                pop_averages[row][col] = self.arr_zones[row][col].collective_population_metric
                enemy_pop_averages[row][col] = self.arr_zones[row][col].enemy_collective_population_metric
                arr_centers[row][col] = self.arr_zones[row][col].center

        # logging.info('inspiring')
        # for i in range(len(inspiring)):
        #     logging.info(inspiring[i])
        logging.info('pop_averages')
        for i in range(len(pop_averages)):
            logging.info(pop_averages[i])

        logging.info('zone averages')
        for i in range(len(ave_halite)):
            logging.info(ave_halite[i])

        logging.info('zone totals')
        for i in range(len(col_halite)):
            logging.info(col_halite[i])

        logging.info('orig adjusted zone averages')
        for i in range(len(orig_cluster_arr)):
            logging.info(orig_cluster_arr[i])

        logging.info('adjusted zone averages')
        for i in range(len(cluster_arr)):
            logging.info(cluster_arr[i])

        return cluster_arr, pop_averages, arr_centers, enemy_pop_averages, individual_arr

    def coordinate_dropoff_v2(self, game):
        cluster_arr, pop_averages, arr_centers, enemy_pop_averages, individual_arr = self.check_map_averages(game, logging)
        dict_values = {}
        dict_pops = {}
        dict_enemy_pops = {}
        dict_centers = {}
        dict_unblended = {}

        for row in range(len(cluster_arr)):
            for col in range(len(cluster_arr)):
                dict_values['{},{}'.format(row,col)] = cluster_arr[row][col]
                dict_pops['{},{}'.format(row,col)] = pop_averages[row][col]
                dict_enemy_pops['{},{}'.format(row,col)] = enemy_pop_averages[row][col]
                dict_centers['{},{}'.format(row,col)] = arr_centers[row][col]
                dict_unblended['{},{}'.format(row,col)] = individual_arr[row][col]

        logging.info(dict_values)
        logging.info(dict_pops)
        logging.info('considering dropoffs at turn: {}'.format(game.turn_number))
        s_best_loc = sorted(dict_values, key = dict_values.get, reverse = True)[0]
        best_value = dict_values[s_best_loc]

        # if len(game.players) == 2:
        #     dict_values = {key: dict_values[key] for key in dict_values.keys() if
        #                    dict_values[key] >= best_value * 0.9 and dict_values[
        #                        key] >= self.dropoff_thresholds.cluster_arr_threshold}
        # else:
        #     dict_values = {key: dict_values[key] for key in dict_values.keys() if
        #                    dict_values[key] >= best_value * 0.9}
        failed = True
        for iter in [0.9,0.8,0.7,0.6]:
            loop_dict_values = dict_values.copy()
            loop_dict_values = {key: loop_dict_values[key] for key in loop_dict_values.keys() if
                                loop_dict_values[key] >= best_value * iter and loop_dict_values[
                               key] >= self.dropoff_thresholds.cluster_arr_threshold}
            loop_dict_values = {key: loop_dict_values[key] for key in loop_dict_values.keys() if
                           (dict_enemy_pops[key] >= self.dropoff_thresholds.enemy_pop_average_treshold and dict_pops[
                               key] > self.dropoff_thresholds.pop_averages_threshold) \
                           or dict_enemy_pops[key] < self.dropoff_thresholds.enemy_pop_average_treshold}
            # loop_dict_values = {key: dict_unblended[key] for key in loop_dict_values.keys() if
            #                     dict_unblended[key] > max([dict_unblended[key] for key in loop_dict_values.keys()]) * 0.6}
            if len(loop_dict_values) > 0:
                dict_values = loop_dict_values
                failed = False
                break
        if failed:
            game.check_for_dropoffs = False
            return

        if len(dict_values) == 0:
            game.check_for_dropoffs = False
            return
        dict_pops = {key : dict_pops[key] for key in dict_values.keys()}
        logging.info(dict_values)
        logging.info(dict_pops)

        if sum(dict_pops.values()) == 0:
            dict_dist = { key : game.game_map.calculate_distance(game.me.shipyard.position, dict_centers[key]) for key in dict_values.keys()}
            logging.info('searching by distance')
            logging.info(dict_dist)
            s_best_loc = sorted(dict_dist, key = dict_dist.get)[0]
            best_value = dict_values[s_best_loc]
        else:
            s_best_loc = sorted(dict_pops, key = dict_pops.get, reverse = True)[0]
            best_value = dict_values[s_best_loc]
        logging.info(s_best_loc)
        logging.info(best_value)

        # if best_value < 8000:
        #     game.check_for_dropoffs = False
        #     return

        best_loc = [int(s_best_loc.split(',')[0]), int(s_best_loc.split(',')[1])]
        self.next_dropoff_zone = self.arr_zones[best_loc[0]][best_loc[1]]
        logging.info('best zone for dropoff: {}'.format(self.next_dropoff_zone))

        target = self.next_dropoff_zone.center

        self.influence_target_pos = target
        logging.info('influence_target_pos: {}'.format(self.influence_target_pos))
        self.influence_number_of_ships = 15
        self.adjust_halite_in_bank = constants.DROPOFF_COST

    def coordinate_dropoff(self, game, logging):
        cluster_arr, pop_averages, arr_centers, enemy_pop_averages, individual_arr = self.check_map_averages(game, logging)
        best_loc = None
        dict_best_loc = {'1': [-1,-1], '2': [-1,-1], '3':[-1,-1]}
        dict_best_value = {'1': 0, '2': 0, '3': 0}
        for row in range(len(cluster_arr)):
            for col in range(len(cluster_arr)):
                if cluster_arr[row][col] > dict_best_value['1']:
                    dict_best_value['3'] = dict_best_value['2']
                    dict_best_value['2'] = dict_best_value['1']
                    dict_best_value['1'] = cluster_arr[row][col]
                    dict_best_loc['3'] = dict_best_loc['2']
                    dict_best_loc['2'] = dict_best_loc['1']
                    dict_best_loc['1'] = [row, col]
                elif cluster_arr[row][col] > dict_best_value['2']:
                    dict_best_value['3'] = dict_best_value['2']
                    dict_best_value['2'] = cluster_arr[row][col]
                    dict_best_loc['3'] = dict_best_loc['2']
                    dict_best_loc['2'] = [row, col]
                elif cluster_arr[row][col] > dict_best_value['3']:
                    dict_best_value['3'] = cluster_arr[row][col]
                    dict_best_loc['3'] = [row, col]

        for i in ['1','2','3']:
            row = dict_best_loc[i][0]
            col = dict_best_loc[i][1]
            if pop_averages[row][col] > 0:
                best_value = cluster_arr[row][col]
                best_loc = [row,col]
                logging.info('chose the {} best zone'.format(i))
                break
        logging.info(dict_best_value)
        logging.info(dict_best_loc)
        if best_loc is None:
            best_loc = dict_best_loc['1']
            best_value = dict_best_value['1']

        if best_value < 10000 + 20 * game.turn_number:
            return

        self.next_dropoff_zone = self.arr_zones[best_loc[0]][best_loc[1]]
        logging.info('best zone for dropoff: {}'.format(self.next_dropoff_zone))

        source = game.me.shipyard.position
        target = self.next_dropoff_zone.center

        self.influence_target_pos = target
        logging.info('influence_target_pos: {}'.format(self.influence_target_pos))
        self.influence_number_of_ships = 15
        self.adjust_halite_in_bank = constants.DROPOFF_COST

    def reset_dropoff_instructions(self):
        self.adjust_halite_in_bank = 0
        self.next_dropoff_zone = None

    def check_halite_expected(self, game):
        expected_halite = game.me.halite_amount
        for ship in game.me.get_ships():
            if ship.mission == 'go_to_base':
                expected_halite += ship.halite_amount * 0.9
        return expected_halite

    def check_send_ship_to_create_dropoff(self, game):
        if self.check_halite_expected(game) > self.adjust_halite_in_bank \
                and self.next_dropoff_zone is not None:
            self.next_dropoff_zone.assign_closest_ship_to_zone(game)

    def check_still_create_dropoff_v2(self, game):
        cluster_arr, pop_averages, arr_centers, enemy_pop_averages, individual_arr = self.check_map_averages(game, logging)
        row = int(self.next_dropoff_zone.y_start / game.window_size)
        col = int(self.next_dropoff_zone.x_start / game.window_size)
        # if cluster_arr[row][col] < self.dropoff_thresholds.cluster_arr_threshold * 0.6:
        #     logging.info('old method')
        # if cluster_arr[row][col] < self.dropoff_thresholds.cluster_arr_threshold * 0.6 \
        #         or (enemy_pop_averages[row][col] > self.dropoff_thresholds.enemy_pop_average_treshold
        #             and pop_averages[row][col] < self.dropoff_thresholds.pop_averages_threshold):
        #     logging.info('joined_metod')
        if (enemy_pop_averages[row][col] > self.dropoff_thresholds.enemy_pop_average_treshold
                and pop_averages[row][col] < self.dropoff_thresholds.pop_averages_threshold):
            logging.info('changed mind about dropoff')
            self.reset_dropoff_instructions()
            self.influence_number_of_ships = 1
            self.influence_target_pos = Position(0,0)

class DropoffThresholds():
    def __init__(self, game):
        game_map = game.game_map
        if len(game.players) == 2:
            if game_map.width == 32:
                self.two_xs()
            if game_map.width == 40:
                self.two_s()
            if game_map.width == 48:
                self.two_m()
            if game_map.width == 56:
                self.two_l()
            if game_map.width == 64:
                self.two_xl()
        else:
            if game_map.width == 32:
                self.four_xs()
            if game_map.width == 40:
                self.four_s()
            if game_map.width == 48:
                self.four_m()
            if game_map.width == 56:
                self.four_l()
            if game_map.width == 64:
                self.four_xl()

    def two_xs(self):
        # tested 22/12
        self.enemy_pop_average_treshold = 80
        self.cluster_arr_threshold = 8000
        self.pop_averages_threshold = 30
        self.search_distance = 15
        self.variable_ship_cutoff = 3000

    def two_s(self):
        # tested 22/12
        self.enemy_pop_average_treshold = 80
        self.cluster_arr_threshold = 9000
        self.pop_averages_threshold = 30
        self.search_distance = 15
        self.variable_ship_cutoff = 3000

    def two_m(self):
        # tested 22/12
        self.enemy_pop_average_treshold = 60
        self.cluster_arr_threshold = 9500
        self.pop_averages_threshold = 30
        self.search_distance = 20
        self.variable_ship_cutoff = 3000

    def two_l(self):
        self.enemy_pop_average_treshold = 60
        self.cluster_arr_threshold = 10000
        self.pop_averages_threshold = 30
        self.search_distance = 20
        self.variable_ship_cutoff = 3000

    def two_xl(self):
        self.enemy_pop_average_treshold = 60
        self.cluster_arr_threshold = 10000
        self.pop_averages_threshold = 30
        self.search_distance = 20
        self.variable_ship_cutoff = 3000


    def four_xs(self):
        # tested on 22/12
        self.enemy_pop_average_treshold = 1000
        self.cluster_arr_threshold = 2000
        self.pop_averages_threshold = 1000
        self.search_distance = 20
        self.variable_ship_cutoff = 2000

    def four_s(self):
        # tested on 22/12
        self.enemy_pop_average_treshold = 1000
        self.cluster_arr_threshold = 3500
        self.pop_averages_threshold = 1000
        self.search_distance = 20
        self.variable_ship_cutoff = 2000

    def four_m(self):
        # tested on 22/12
        self.enemy_pop_average_treshold = 100
        # self.cluster_arr_threshold = 8500
        self.cluster_arr_threshold = 8000
        self.pop_averages_threshold = 30
        self.search_distance = 20
        self.variable_ship_cutoff = 2000

    def four_l(self):
        # tested on 22/12
        self.enemy_pop_average_treshold = 90
        # self.cluster_arr_threshold = 9000
        self.cluster_arr_threshold = 7000
        self.pop_averages_threshold = 30
        self.search_distance = 20
        self.variable_ship_cutoff = 2000

    def four_xl(self):
        self.enemy_pop_average_treshold = 90
        # self.cluster_arr_threshold = 10000
        self.cluster_arr_threshold = 7000
        self.pop_averages_threshold = 30
        self.search_distance = 20
        self.variable_ship_cutoff = 2000
