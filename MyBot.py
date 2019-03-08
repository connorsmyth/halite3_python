#!/usr/bin/env python3
def main():
    # Python 3.6
    # Logging allows you to save messages for yourself. This is required because the regular STDOUT
    #   (print statements) are reserved for the engine-bot communication.
    import logging
    # This library allows you to generate random numbers.

    import numpy as np
    import common
    from datetime import datetime
    import debug_common



    from hlt.positionals import Position
    np.set_printoptions(threshold=np.nan)

    # Import the Halite SDK, which will let you interact with the game.
    import hlt
    from hlt.enemy_monitor import EnemyMonitor
    # This library contains  constant values.
    from hlt import constants
    turn_timer = {}

    # This library contains direction metadata to better interface with the game.

    """ <<<Game Begin>>> """

    game = hlt.Game()
    coordinator = hlt.entity.Coordinator(game)
    coordinator.generate_game_plan(game, logging)
    enemy_monitor = EnemyMonitor(game)

    game.ready("csmyu_v20")

    # logging.info("Successfully created bot! My Player ID is {}.".format(game.my_id))

    """ <<<Game Loop>>> """

    while True:
        # This loop handles each turn of the game. The game object changes every turn, and you refresh that state by
        #   running update_frame().
        turn_start_time = game.update_frame(coordinator)

        for zone in coordinator.zones.values():
            zone.refresh_values(game)
        game.update_dictionaries(coordinator, logging)
        enemy_monitor.new_round(game)

        # You extract player metadata and the updated map metadata here for convenience.
        me = game.me
        game_map = game.game_map

        # A command queue holds all the commands you will run this turn. You build this list up and submit it at the
        #   end of the turn.
        command_queue = []

        # if game.turn_number >= 10 and constants.MAX_TURNS - game.turn_number > 150 \
        #         and len(game.me.get_ships()) >= 15 and coordinator.next_dropoff_zone is None \
        #         and game_map.get_total_halite() / (len(game.me.get_dropoffs()) + 2) > 30000 + game.turn_number * 20 \
        #         and coordinator.influence_number_of_ships == 0 \
        #         and game.check_for_dropoffs:
        #     coordinator.coordinate_dropoff_v2(game)

        if game.turn_number >= 10 and constants.MAX_TURNS - game.turn_number > 150 \
                and len(game.me.get_ships()) >= 15 and coordinator.next_dropoff_zone is None \
                and game_map.get_total_halite() / (len(game.me.get_dropoffs()) + 2) > 30000 + game.turn_number * 20 \
                and (coordinator.influence_number_of_ships == 0 or game.turn_number > 100 + coordinator.last_dropoff_turn ) \
                and game.check_for_dropoffs:
            coordinator.coordinate_dropoff_v2(game)

        if coordinator.next_dropoff_zone is not None:
            coordinator.check_still_create_dropoff_v2(game)

        coordinator.generate_game_plan(game, logging)
        coordinator.check_send_ship_to_create_dropoff(game)

        for ship in me.get_ships():
            if not debug_common.debug_mode \
                    and (datetime.now() - turn_start_time).total_seconds() > 1.6:
                break
            if ship.id not in game.turn_ship_created.keys():
                game.turn_ship_created[ship.id] = game.turn_number
            logging.info('getting best intention for ship: {}, mission: {}'.format(ship.id, ship.mission))
            ship.get_best_intention(game, game_map, logging, coordinator, command_queue, turn_start_time)

        for attempt_no in range(1,7):
            if not debug_common.debug_mode \
                    and (datetime.now() - turn_start_time).total_seconds() > 1.8:
                break
            if attempt_no == 1:
                game_map.resolve_swaps(me, command_queue)
            if attempt_no == 5:
                game_map.resolve_swaps(me, command_queue, second_choice=True)
            for ship in [ship for ship in me.get_ships() if not ship.command_sent]:
                single_instruction = ship.resolve_intention(game, game_map, attempt_no)
                if single_instruction is not None:
                    command_queue.append(single_instruction)

        coordinator.check_generate_new_ship(game, command_queue)

        game.game_missions = {ship.id : ship.mission for ship in me.get_ships()}
        game.still_counts = {ship.id : ship.still_count for ship in me.get_ships()}
        game.last_positions = {ship.id : ship.position for ship in me.get_ships()}

        # game.dict_positions = game_map.get_marked_position(me)
        coordinator.assigned_target_squares = {ship.id : ship.target_square for ship in me.get_ships() if ship.target_square is not None}

        logging.info('total_halite: {}, min_halite_to_take: {}, total_halite: {}, ship_count: {}'.format(game.game_map.get_total_halite(), game.min_halite_to_take, game.me.halite_amount, len(game.me.get_ships())))
        if game.turn_number == constants.MAX_TURNS:
            keylist = list(game.turn_ship_created.keys())
            for key in keylist:
                if key not in game.total_halite_for_ship.keys():
                    game.total_halite_for_ship[key] = 0
                logging.info("id: {}, tot_hlt: {}, Created on: {}".format(key, game.total_halite_for_ship[key], game.turn_ship_created[key]))
            logging.info(turn_timer)

        turn_timer[game.turn_number] = (datetime.now() - turn_start_time).total_seconds()
        if debug_common.debug_mode:
            print(game.turn_number)
        game.end_turn(command_queue)

    # improvements:
    #       -when a ship is close to filling up
    #           it is best that they are done closer to the dropoff
    #       - weigh zones better if they are close to an opponent
    #           (in terms of getting inspiration)

# get idea of what you think the opponent should do.
# if you think they'll stay then the cells around them are safe
# if you think they'll move then you shouldn't go there.

# inspired zones
# recalculating zone if going to zone and surrounded


main()

# logging.info('seems to be stuck, going to base early')
# logging.info('passively collided with ship')
# logging.info('decided to go as still for too long')

# aggressive enemy takedown
