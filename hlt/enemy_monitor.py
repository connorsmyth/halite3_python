from .positionals import Position

class EnemyMonitor():
    def __init__(self, game):
        self.enemy_ship_missions = {}
        self.ship_still = {}
        return

    def new_round(self, game):
        game_map = game.game_map
        self.me_pos_base = [entity.position for entity in game.me.get_dropoffs_and_shipyard()]
        other_players = [player for player in game.players.values() if player.id != game.me.id]

        self.check_still(game, other_players)
        for player in other_players:
            for ship in player.get_ships():
                self.check_inspired(player, game, game_map, ship)
                self.update_mission(ship)
                self.check_option_to_down(game, game_map, ship)
                self.predict_next_move(game, game_map, ship)
                self.check_ignore_ship(game, game_map, ship)

        for pos in self.me_pos_base:
            game_map[pos].enemy_intention = False
            for x in range(-4,5):
                for y in range(-4,5):
                    if abs(x) + abs(y) <= 4:
                        norm_pos = game_map.normalize(pos + Position(x,y))
                        cell = game_map[norm_pos]
                        cell.two_p_dangerous = False

        self.save_values_for_round(game)
        return

    def check_inspired(self, player, game, game_map, ship):
        if len(game.players) == 2:
            counter = 0
            for x in range(-4,5):
                for y in range(-4,5):
                    if abs(x) + abs(y) <= 4:
                        pos = game_map.normalize(ship.position + Position(x,y))
                        cell = game_map[pos]
                        if cell.is_occupied:
                            if cell.ship.owner != player.id:
                                counter += 1
            if counter >= 2:
                ship.enemy_inspired = True
                ship.enemy_expected_value_if_still = min(1000, ship.halite_amount + game_map[ship.position].halite_amount * 0.75)
                ship.enemy_still_to_gain = min(1000 - ship.halite_amount, game_map[ship.position].halite_amount * 0.75)
            else:
                ship.enemy_expected_value_if_still = min(1000, ship.halite_amount + game_map[ship.position].halite_amount * 0.25)
                ship.enemy_still_to_gain = min(1000 - ship.halite_amount, game_map[ship.position].halite_amount * 0.25)
        return

    def check_still(self, game, other_players):
        for player in other_players:
            for ship in player.get_ships():
                if ship.id in self.ship_positions.keys():
                    if ship.position == self.ship_positions[ship.id]:
                        if ship.id in self.ship_still.keys():
                            self.ship_still[ship.id] += 1
                        else:
                            self.ship_still[ship.id] = 1
                    else:
                        if ship.id in self.ship_still.keys():
                            self.ship_still.pop(ship.id)

        return

    def check_option_to_down(self, game, game_map, ship):
        if ship.halite_amount == 1000 and ship.id in self.ship_still.keys():
            if self.ship_still[ship.id] > 3:
                ship.enemy_takedown_ship_passive = True
                game_map[ship.position].enemy_passive_takedown = True
        if len(game.players) == 2:
            # if ship.halite_amount > 600 or ship.enemy_still_to_gain > 300:
            if ship.enemy_expected_value_if_still > 500:
                counter = 0
                enemy_counter = 0
                search_space = 5
                for x in range(-search_space,search_space+1):
                    for y in range(-search_space,search_space+1):
                        if abs(x) + abs(y) <= 4:
                            norm_pos = game_map.normalize(ship.position + Position(x,y))
                            cell = game_map[norm_pos]
                            if cell.is_occupied:
                                if cell.ship.owner == game.me.id:
                                    counter += 1
                                else:
                                    enemy_counter += 1
                if counter >= 2 or enemy_counter <= 1:
                    ship.enemy_takedown_ship = True
                # game_map[ship.position].enemy_takedown = True
        return

    def check_ignore_ship(self, game, game_map, ship):

        if ship.position in self.me_pos_base:
            game_map[ship.position].mark_safe()

    def update_map_pos_v2(self, game_map, ship):
        game_map[ship.position].enemy_intention = True

    def predict_next_move(self, game, game_map, ship):
        # if len(game.players) == 4 or ship.enemy_takedown_ship:
        if len(game.players) == 4:
            self.predict_next_move_four(game, game_map, ship)
            self.predict_next_move_two(game, game_map, ship)
        # elif ship.enemy_takedown_ship:
        #     self.predict_next_move_four(game, game_map, ship, target=True)
        elif len(game.players) == 2:
            self.predict_next_move_two(game, game_map, ship)

    def predict_next_move_two(self, game, game_map, ship):
        norm_pos = [game_map.normalize(pos) for pos in ship.position.get_surrounding_cardinals()]
        for pos in norm_pos:
            game_map[pos].two_p_dangerous = True

    def predict_next_move_four(self, game, game_map, ship):

        if ship.mission == 'enemy_return_to_base':
            best_dropoff = game.players[ship.owner].shipyard
            for entity in game.players[ship.owner].get_dropoffs():
                if game_map.calculate_distance(ship.position, entity.position) < game_map.calculate_distance(ship.position, best_dropoff.position):
                    best_dropoff = entity
            best_dirs = game_map.naive_navigate(ship, best_dropoff.position, list_best = True)
            if type(best_dirs) == tuple:
                best_pos = game_map.normalize(ship.position + Position(*best_dirs))
                game_map[best_pos].enemy_intention = True
            else:
                for dir in list(best_dirs):
                    best_pos = game_map.normalize(ship.position + Position(*dir))
                    game_map[best_pos].enemy_intention = True

        elif ship.mission == 'enemy_collect':
            intentions = ship.best_four_moves_enemy(game, game_map)
            if type(intentions) == tuple: intentions = [intentions]
            for intention in intentions:
                new_pos = game_map.normalize(ship.position + Position(*intention))
                game_map[new_pos].enemy_intention = True

            # if game_map[ship.position].halite_amount > game.min_halite_to_take:
            #     self.update_map_pos_v2(game_map, ship)
            #     return
            # # elif len(game.me.get_ships()) < 110:
            # elif True:
            #     intentions = ship.best_four_moves_enemy(game, game_map)
            #     if type(intentions) == tuple: intentions = [intentions]
            #     for intention in intentions:
            #         new_pos = game_map.normalize(ship.position + Position(*intention))
            #         game_map[new_pos].enemy_intention = True
            #
            # else:
            #     norm_pos = [game_map.normalize(pos) for pos in ship.position.get_surrounding_cardinals()]
            #     norm_pos = [pos for pos in norm_pos if not game_map[pos].is_occupied]
            #     halite_pos = {pos: game_map[pos].halite_amount for pos in norm_pos}
            #     halite_pos = {key: halite_pos[key] for key in halite_pos.keys() if
            #                   halite_pos[key] > 0.8 * max(halite_pos.values())}
            #
            #     if len(halite_pos) == 0:
            #         # self.update_map_pos(game_map, ship)
            #         game_map[ship.position].enemy_intention = True
            #         return
            #     for pos in halite_pos.keys():
            #         game_map[ship.position].enemy_intention = True
            #         return

        return

    def update_mission(self, ship):
        if ship.id in self.enemy_ship_missions.keys():
            ship.mission = self.enemy_ship_missions[ship.id]
        if ship.mission == '':
            ship.mission = 'enemy_collect'
        if ship.halite_amount > 900:
            ship.mission = 'enemy_return_to_base'
        if ship.halite_amount < 400:
            ship.mission = 'enemy_collect'

    def save_values_for_round(self, game):
        self.enemy_ship_missions = {}
        self.ship_positions = {}
        for player in [player for player in game.players.values() if player.id != game.me.id]:
            for ship in player.get_ships():
                self.enemy_ship_missions[ship.id] = ship.mission
                self.ship_positions[ship.id] = ship.position