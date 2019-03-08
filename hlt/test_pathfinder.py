from pathfinding.core.diagonal_movement import DiagonalMovement
from pathfinding.core.grid import Grid
from pathfinding.finder.a_star import AStarFinder
import copy

def test():
    matrix = [
      [1, 10, 1, 1, 1],
      [1, 1, 1, 1, 1],
      [1, 11, 1, 1, 1, 1],
      [1, 1000, 1, 1, 1, 1],
      [1, 10, 1, 7, 19, 1]
    ]

    grid = Grid(matrix=matrix, wrap = True)

    start = grid.node(2, 3)
    end = grid.node(0, 3)

    finder = AStarFinder(diagonal_movement=DiagonalMovement.never)
    path, runs = finder.find_path(start, end, grid)

    print('operations:', runs, 'path length:', len(path))
    print(grid.grid_str(path=path, start=start, end=end))

def find_path(orig_grid,start, end, time_limit, wrap = False):
    # grid = Grid(matrix=matrix, wrap = wrap)
    grid = copy.deepcopy(orig_grid)
    start = grid.node(start.y, start.x)
    end = grid.node(end.y, end.x)

    finder = AStarFinder(diagonal_movement=DiagonalMovement.never, time_limit = time_limit)
    path, runs = finder.find_path(start, end, grid)

    return path

def create_grid_and_find_path(matrix, start, end,time_limit, wrap = False):
    grid = Grid(matrix=matrix, wrap = wrap)

    start = grid.node(start.x, start.y)
    end = grid.node(end.x, end.y)

    # finder = AStarFinder(diagonal_movement=DiagonalMovement.never, heuristic='world_wrap')
    finder = AStarFinder(diagonal_movement=DiagonalMovement.never, time_limit=time_limit, heuristic='world_wrap')

    path, runs = finder.find_path(start, end, grid)

    return path

# test()