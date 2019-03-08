import queue

from . import constants
from .entity import Entity, Shipyard, Ship, Dropoff
from .positionals import Direction, Position
from .common import read_input
import logging


class Player:
    """
    Player object containing all items/metadata pertinent to the player.
    """
    def __init__(self, player_id, shipyard, halite=0):
        self.id = player_id
        self.shipyard = shipyard
        self.halite_amount = halite
        self._ships = {}
        self._dropoffs = {}

    def get_ship(self, ship_id):
        """
        Returns a singular ship mapped by the ship id
        :param ship_id: The ship id of the ship you wish to return
        :return: the ship object.
        """
        return self._ships[ship_id]

    def get_ships(self):
        """
        :return: Returns all ship objects in a list
        """
        return list(self._ships.values())

    def get_ship_ids(self):
        return list(self._ships.keys())

    def get_dropoff(self, dropoff_id):
        """
        Returns a singular dropoff mapped by its id
        :param dropoff_id: The dropoff id to return
        :return: The dropoff object
        """
        return self._dropoffs[dropoff_id]

    def get_dropoffs(self):
        """
        :return: Returns all dropoff objects in a list
        """
        if len(self._dropoffs) == 0:
            return list()
        else:
            return list(self._dropoffs.values())

    def get_dropoffs_and_shipyard(self):
        """
        :return: Returns all dropoff objects in a list
        """
        if len(self._dropoffs) == 0:
            return [self.shipyard]
        else:
            return list(self._dropoffs.values()) + [self.shipyard]

    def has_ship(self, ship_id):
        """
        Check whether the player has a ship with a given ID.

        Useful if you track ships via IDs elsewhere and want to make
        sure the ship still exists.

        :param ship_id: The ID to check.
        :return: True if and only if the ship exists.
        """
        return ship_id in self._ships


    @staticmethod
    def _generate():
        """
        Creates a player object from the input given by the game engine
        :return: The player object
        """
        player, shipyard_x, shipyard_y = map(int, read_input().split())
        return Player(player, Shipyard(player, -1, Position(shipyard_x, shipyard_y)))

    def _update(self, num_ships, num_dropoffs, halite):
        """
        Updates this player object considering the input from the game engine for the current specific turn.
        :param num_ships: The number of ships this player has this turn
        :param num_dropoffs: The number of dropoffs this player has this turn
        :param halite: How much halite the player has in total
        :return: nothing.
        """
        self.halite_amount = halite
        self._ships = {id: ship for (id, ship) in [Ship._generate(self.id) for _ in range(num_ships)]}
        self._dropoffs = {id: dropoff for (id, dropoff) in [Dropoff._generate(self.id) for _ in range(num_dropoffs)]}


class MapCell:
    """A cell on the game map."""
    def __init__(self, position, halite_amount):
        self.position = position
        self.halite_amount = halite_amount
        self.adjusted_halite_amount = halite_amount
        self.ship = None
        self.structure = None
        self.targeted = None
        self.ship_return_no_go = None
        self.is_inspiring = 0
        # self.is_dangerous = False
        # self.fair_game = False
        self.min_distance_to_dropoff = 1000
        self.halite_to_count_for_new_dropoffs = 0
        self.population_metric = 0
        self.enemy_population_metric = 0
        self.close_to_my_dropoff = False
        self.enemy_intention = False
        # self.enemy_takedown = False
        self.enemy_takedown_ship = None
        self.enemy_passive_takedown = False
        self.two_p_dangerous = False

    @property
    def halite_incl_inspired(self):
        return self.halite_amount if self.is_inspiring < 2 else 3 * self.halite_amount

    @property
    def is_empty(self):
        """
        :return: Whether this cell has no ships or structures
        """
        return self.ship is None and self.structure is None

    @property
    def is_occupied(self):
        """
        :return: Whether this cell has any ships
        """
        return self.ship is not None

    @property
    def has_structure(self):
        """
        :return: Whether this cell has any structures
        """
        return self.structure is not None

    @property
    def structure_type(self):
        """
        :return: What is the structure type in this cell
        """
        return None if not self.structure else type(self.structure)
    def mark_target(self, ship):
        self.targeted = ship.id

    def is_targeted(self):
        return self.targeted is not None

    def mark_unsafe(self, ship):
        """
        Mark this cell as unsafe (occupied) for navigation.

        Use in conjunction with GameMap.naive_navigate.
        """
        self.ship = ship

    def mark_safe(self):
        self.ship = None

    def __eq__(self, other):
        return self.position == other.position

    def __ne__(self, other):
        return not self.__eq__(other)

    def __str__(self):
        return 'MapCell({}, halite={})'.format(self.position, self.halite_amount)


class GameMap:
    """
    The game map.

    Can be indexed by a position, or by a contained entity.
    Coordinates start at 0. Coordinates are normalized for you
    """
    def __init__(self, cells, width, height):
        self.width = width
        self.height = height
        self._cells = cells
        self._calculated_tot_halite = False

    def __getitem__(self, location):
        """
        Getter for position object or entity objects within the game map
        :param location: the position or entity to access in this map
        :return: the contents housing that cell or entity
        """
        if isinstance(location, Position):
            location = self.normalize(location)
            return self._cells[location.y][location.x]
        elif isinstance(location, Entity):
            return self._cells[location.position.y][location.position.x]
        return None

    def calculate_distance(self, source, target):
        """
        Compute the Manhattan distance between two locations.
        Accounts for wrap-around.
        :param source: The source from where to calculate
        :param target: The target to where calculate
        :return: The distance between these items
        """
        source = self.normalize(source)
        target = self.normalize(target)
        resulting_position = abs(source - target)
        return min(resulting_position.x, self.width - resulting_position.x) + \
            min(resulting_position.y, self.height - resulting_position.y)

    def normalize(self, position):
        """
        Normalized the position within the bounds of the toroidal map.
        i.e.: Takes a point which may or may not be within width and
        height bounds, and places it within those bounds considering
        wraparound.
        :param position: A position object.
        :return: A normalized position object fitting within the bounds of the map
        """
        return Position(position.x % self.width, position.y % self.height)

    @staticmethod
    def _get_target_direction(source, target):
        """
        Returns where in the cardinality spectrum the target is from source. e.g.: North, East; South, West; etc.
        NOTE: Ignores toroid
        :param source: The source position
        :param target: The target position
        :return: A tuple containing the target Direction. A tuple item (or both) could be None if within same coords
        """
        return (Direction.South if target.y > source.y else Direction.North if target.y < source.y else None,
                Direction.East if target.x > source.x else Direction.West if target.x < source.x else None)

    def get_unsafe_moves(self, source, destination):
        """
        Return the Direction(s) to move closer to the target point, or empty if the points are the same.
        This move mechanic does not account for collisions. The multiple directions are if both directional movements
        are viable.
        :param source: The starting position
        :param destination: The destination towards which you wish to move your object.
        :return: A list of valid (closest) Directions towards your target.
        """
        source = self.normalize(source)
        destination = self.normalize(destination)
        possible_moves = []
        distance = abs(destination - source)
        y_cardinality, x_cardinality = self._get_target_direction(source, destination)

        if distance.x != 0:
            possible_moves.append(x_cardinality if distance.x < (self.width / 2)
                                  else Direction.invert(x_cardinality))
        if distance.y != 0:
            possible_moves.append(y_cardinality if distance.y < (self.height / 2)
                                  else Direction.invert(y_cardinality))
        return possible_moves

    def direct_traffic(self, ship_dock):
        for offset in [-3,-2,-1,1,2,3]:
            self[self.normalize(ship_dock.position + Position(0, offset))].ship_return_no_go = True

    def planned_navigate(self, ship, destination, ignore_direction=None, best_intention=False):
        intentions = self.naive_navigate_v2(ship.position, ship.halite_amount, destination, ignore_direction, best_intention)
        if type(intentions) == tuple:
            intentions = [intentions]
        dict_results = {}
        for iter in range(len(intentions)):
            intent = intentions[iter]
            new_pos = self.normalize(ship.position + Position(*intent))
            dict_results[iter] = self[new_pos].halite_amount * 0.1
            sec_intentions = self.naive_navigate_v2(new_pos, ship.halite_amount, destination, best_intention=False)
            if type(sec_intentions) == tuple:
                if sec_intentions == Direction.Still:
                    dict_results[iter] += 1000

        best_order = sorted(dict_results, key=dict_results.get, reverse=False)
        intentions = [intentions[i] for i in best_order]
        if len(intentions) == 1:
            return intentions[0]
        return intentions

    def naive_navigate_v2(self, position, ship_halite, destination, ignore_direction = None, best_intention = False):
        cost = 10000
        dict_dirs = {}
        final_direction = Direction.Still
        for direction in self.get_unsafe_moves(position, destination):
            if str(direction) != str(ignore_direction):
                target_pos = position.directional_offset(direction)
                if not self[target_pos].enemy_intention or best_intention:
                    if not self[target_pos].is_occupied or best_intention:
                        dict_dirs[direction] = self[target_pos].halite_amount
                        if self[target_pos].halite_amount < cost:
                            cost = self[target_pos].halite_amount
                            final_direction = direction

        if best_intention and len(dict_dirs) > 1:
            list_best_directions = sorted(dict_dirs, key=dict_dirs.get, reverse=False)
            return list_best_directions
        return final_direction

    def naive_navigate(self, ship, destination, ignore_direction = None, best_intention = False, list_best = False):
        """
        Returns a singular safe move towards the destination, which is the cheapest safe move.

        :param ship: The ship to move.
        :param destination: Ending position
        :return: A direction.
        """
        # No need to normalize destination, since get_unsafe_moves
        # does that
        cost = 10000
        dict_dirs = {}
        final_direction = Direction.Still
        for direction in self.get_unsafe_moves(ship.position, destination):
            if str(direction) != str(ignore_direction):
                target_pos = ship.position.directional_offset(direction)
                if not self[target_pos].enemy_intention or best_intention:
                    if not self[target_pos].is_occupied or best_intention:
                        dict_dirs[direction] = self[target_pos].halite_amount
                        if self[target_pos].halite_amount < cost:
                            cost = self[target_pos].halite_amount
                            final_direction = direction

        if (best_intention or list_best) and len(dict_dirs) > 1:
            list_best_directions = sorted(dict_dirs, key=dict_dirs.get, reverse=False)
            return list_best_directions
        return final_direction


    @staticmethod
    def _generate():
        """
        Creates a map object from the input given by the game engine
        :return: The map object
        """
        map_width, map_height = map(int, read_input().split())
        game_map = [[None for _ in range(map_width)] for _ in range(map_height)]
        for y_position in range(map_height):
            cells = read_input().split()
            for x_position in range(map_width):
                game_map[y_position][x_position] = MapCell(Position(x_position, y_position),
                                                           int(cells[x_position]))
        return GameMap(game_map, map_width, map_height)

    def get_total_halite(self):
        if self._calculated_tot_halite:
            return self.total_halite
        else:
            tot_halite = 0
            for y in range(self.height):
                for x in range(self.width):
                    tot_halite += self[Position(x, y)].halite_amount
            self.total_halite = tot_halite
            self._calculated_tot_halite = True
            return self.total_halite

    def _update(self, arr_dropoffs, coordinator):
        """
        Updates this map object from the input given by the game engine
        :return: nothing
        """
        # Mark cells as safe for navigation (will re-mark unsafe cells
        # later)
        for y in range(self.height):
            for x in range(self.width):
                cell = self[Position(x, y)]
                cell.ship = None
                cell.ship_return_no_go = None
                cell.targeted = None
                cell.is_inspiring = 0

                cell.enemy_intention = False
                cell.enemy_passive_takedown = False
                # cell.enemy_takedown = False
                cell.enemy_takedown_ship = None
                cell.two_p_dangerous = False

                cell.population_metric = 0
                cell.enemy_population_metric = 0
                cell.close_to_my_dropoff = False


        for _ in range(int(read_input())):
            cell_x, cell_y, cell_energy = map(int, read_input().split())
            self[Position(cell_x, cell_y)].halite_amount = cell_energy
            self[Position(cell_x, cell_y)].adjusted_halite_amount = cell_energy

        tot_halite = 0
        for y in range(self.height):
            for x in range(self.width):
                tot_halite += self[Position(x, y)].halite_amount
                min_distance_to_dropoff = min([self.calculate_distance(Position(x, y), entity.position) for entity in arr_dropoffs])
                # self[Position(x, y)].min_distance_to_dropoff = min_distance_to_dropoff
                self[Position(x, y)].halite_to_count_for_new_dropoffs = min(1, 1.2 ** (min_distance_to_dropoff - coordinator.dropoff_thresholds.search_distance)) * self[Position(x, y)].halite_amount
        self.total_halite = tot_halite

    def reset_adjusted_halite_amount(self, arr_all_pos_used):
        for pos in arr_all_pos_used:
            self[pos].adjusted_halite_amount = self[pos].halite_amount

    def resolve_swaps(self, me, command_queue, second_choice = None):
        if second_choice is None:
            modifier = 1
        else:
            modifier = 5
        for ship in [ship for ship in me.get_ships() if not ship.command_sent]:
            for comparison_ship in [ship for ship in me.get_ships() if not ship.command_sent]:
                if ship.id != comparison_ship.id \
                        and not ship.command_sent and not comparison_ship.command_sent \
                        and self.normalize(ship.position + ship.best_intention_pos(modifier)) == self.normalize(comparison_ship.position) \
                        and self.normalize(comparison_ship.position + comparison_ship.best_intention_pos()) == self.normalize(ship.position):
                    if second_choice:
                        logging.info('swapped ships based on their second choice')
                        logging.info('ship ids: {} and {}'.format(ship.id, comparison_ship.id))
                    single_instruction = ship.move(ship.get_intention(modifier))
                    ship.command_sent = True
                    self[self.normalize(ship.position + Position(*ship.get_intention(modifier)))].mark_unsafe(ship)
                    command_queue.append(single_instruction)
                    single_instruction = comparison_ship.move(comparison_ship.get_intention())
                    comparison_ship.command_sent = True
                    self[self.normalize(comparison_ship.position + Position(*comparison_ship.get_intention()))].mark_unsafe(comparison_ship)
                    command_queue.append(single_instruction)

    def get_marked_position(self, me):
        dict_positions = {}
        for x in range(self.width):
            for y in range(self.height):
                if self[Position(x,y)].ship is not None:
                    if self[Position(x,y)].ship.owner == me.id:
                        dict_positions[self[Position(x,y)].ship.id] = Position(x,y)
        return dict_positions