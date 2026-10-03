using Godot;
using Kinloom.Core;

namespace Valley;

/// <summary>Builds Asagiri from code: autotiled ground and paths, the river and its bridge, rice paddies,
/// buildings, forest and props. Owns the walkability grid and the A* pathfinder used by every character.</summary>
public partial class WorldMap : Node2D
{
    public const int W = 108, H = 44, T = 16;
    /// <summary>The village sits east of the forest: authored village coordinates are shifted by OX.</summary>
    public const int OX = 36;

    public bool[,] Blocked { get; } = new bool[W, H];
    private readonly bool[,] _reserved = new bool[W, H];
    public AStarGrid2D Astar { get; } = new();
    /// <summary>Everything that must be depth-sorted with characters (buildings, trees, actors).</summary>
    public Node2D Entities { get; } = new() { Name = "Entities", YSortEnabled = true };
    public List<Vector2> Lanterns { get; } = new();
    public List<Node2D> FestivalDecor { get; } = new();
    public Dictionary<string, Vector2> Doors { get; } = new();

    private TileMapLayer _ground = null!;
    private TileMapLayer _water = null!;
    private TileMapLayer _field = null!;
    private readonly RandomNumberGenerator _rng = new() { Seed = 7 };

    public static Vector2 ToWorld(Vec2 v) => new(v.X * T + T / 2f, v.Y * T + T / 2f);
    public static Vec2 ToSim(Vector2 p) => new((p.X - T / 2f) / T, (p.Y - T / 2f) / T);
    public static Vector2I Cell(Vector2 p) => new((int)Mathf.Floor(p.X / T), (int)Mathf.Floor(p.Y / T));
    public static Vector2 CellCenter(Vector2I c) => new(c.X * T + T / 2f, c.Y * T + T / 2f);

    public void Build(World world)
    {
        _ground = new TileMapLayer { Name = "Ground", TileSet = GD.Load<TileSet>("res://assets/tiles/floor.tres") };
        _water = new TileMapLayer { Name = "Water", TileSet = AtlasTileSet("tiles/water.png") };
        _field = new TileMapLayer { Name = "Field", TileSet = AtlasTileSet("tiles/field.png") };
        AddChild(_ground);
        AddChild(_field);
        AddChild(_water);
        AddChild(Entities);

        var grass = new Godot.Collections.Array<Vector2I>();
        for (int x = 0; x < W; x++)
            for (int y = 0; y < H; y++) grass.Add(new Vector2I(x, y));
        _ground.SetCellsTerrainConnect(grass, 0, 0);

        PaintPaths();
        PaintRiver();
        PaintFields(57 + OX, 31, 10, 8);
        PlaceBuildings(world);
        PlaceProps();
        PlantForest();
        BuildPathfinder();
    }

    // ---------------------------------------------------------------- ground

    private readonly List<Vector2I> _dirt = new();

    private void Dirt(int x0, int y0, int x1, int y1) => DirtAbs(x0 + OX, y0, x1 + OX, y1);

    private void DirtAbs(int x0, int y0, int x1, int y1)
    {
        for (int x = Math.Min(x0, x1); x <= Math.Max(x0, x1); x++)
            for (int y = Math.Min(y0, y1); y <= Math.Max(y0, y1); y++)
                if (x >= 0 && y >= 0 && x < W && y < H)
                {
                    _dirt.Add(new Vector2I(x, y));
                    _reserved[x, y] = true;
                }
    }

    /// <summary>Two-tile-wide road: horizontal first, then vertical.</summary>
    private void Road(int x0, int y0, int x1, int y1)
    {
        Dirt(x0, y0, x1, y0 + 1);
        Dirt(x1, y0, x1 + 1, y1);
    }

    private void RoadAbs(int x0, int y0, int x1, int y1)
    {
        DirtAbs(x0, y0, x1, y0 + 1);
        DirtAbs(x1, y0, x1 + 1, y1);
    }

    private void PaintPaths()
    {
        Dirt(30, 18, 42, 26);            // market square
        Road(2, 21, 30, 21);             // forest trail, bridge, into the square
        Road(30, 19, 26, 15);            // bakery
        Road(26, 14, 18, 14);            // Mira's house
        Road(42, 19, 46, 15);            // forge
        Road(46, 19, 58, 17);            // headman
        Dirt(35, 9, 37, 18);             // shrine avenue
        Dirt(33, 7, 39, 11);             // shrine court
        Road(47, 12, 52, 12); Road(52, 10, 55, 9); // Goro's house
        Road(32, 26, 32, 31); Road(32, 31, 25, 31); Dirt(22, 30, 28, 33); // tea house yard
        Road(25, 33, 20, 33); Road(20, 33, 18, 37); // healer
        Road(40, 26, 40, 31); Road(40, 31, 48, 31); Dirt(45, 30, 51, 33); // guard post yard
        Road(42, 24, 56, 24); Road(56, 24, 64, 26); // farm road
        Road(56, 25, 56, 30);            // to the paddies
        Dirt(13, 23, 17, 27);            // riverside camp
        // the forest (absolute coordinates, west of the river)
        RoadAbs(3, 21, 44, 21);          // the old trail
        RoadAbs(9, 21, 9, 12);           // up to the bandit camp
        DirtAbs(4, 6, 15, 14);           // bandit camp clearing
        RoadAbs(15, 23, 15, 31);         // down to the glade
        DirtAbs(10, 31, 19, 37);         // mushroom glade
        RoadAbs(32, 20, 32, 9);          // up to the spirit grove
        DirtAbs(28, 4, 36, 10);          // spirit grove
        DirtAbs(21, 19, 27, 25);         // clearing on the trail
        _ground.SetCellsTerrainConnect(new Godot.Collections.Array<Vector2I>(_dirt), 0, 1);
    }

    private static TileSet AtlasTileSet(string png)
    {
        var set = new TileSet { TileSize = new Vector2I(T, T) };
        set.AddSource(new TileSetAtlasSource { Texture = Assets.Tex(png), TextureRegionSize = new Vector2I(T, T) }, 0);
        return set;
    }

    private static void SetTile(TileMapLayer layer, Vector2I cell, Vector2I atlas)
    {
        var source = (TileSetAtlasSource)layer.TileSet.GetSource(0);
        if (!source.HasTile(atlas)) source.CreateTile(atlas);
        layer.SetCell(cell, 0, atlas);
    }

    public const int RiverX = 10 + OX;

    private void PaintRiver()
    {
        for (int y = 0; y < H; y++)
        {
            bool bridge = y >= 21 && y <= 22;
            SetTile(_water, new Vector2I(RiverX, y), new Vector2I(0, 7));
            SetTile(_water, new Vector2I(RiverX + 1, y), new Vector2I(1, 7));
            SetTile(_water, new Vector2I(RiverX + 2, y), new Vector2I(2, 7));
            for (int x = RiverX; x <= RiverX + 2; x++)
            {
                _reserved[x, y] = true;
                if (!bridge) Blocked[x, y] = true;
            }
        }
        // bridge planks over the water
        for (int x = RiverX - 1; x <= RiverX + 3; x++)
        {
            int col = x == RiverX - 1 ? 0 : x == RiverX + 3 ? 2 : 1;
            SetTile(_water, new Vector2I(x, 21), new Vector2I(col, 12)); // deck with its top edge
            SetTile(_water, new Vector2I(x, 22), new Vector2I(col, 14)); // bottom edge and supports
            // railings on both sides (the player walks between them)
            // far rail: drawn on the bridge layer (above water, below every walker)
            AddChild(new Sprite2D { Texture = Assets.Region("tiles/house.png", new Rect2(176, 112, 16, 16)), Centered = false, Position = new Vector2(x * T, 21 * T - 9) });
            Prop("tiles/house.png", new Rect2(176, 112, 16, 16), new Vector2I(x, 22), false);
        }
        Prop("tiles/water.png", new Rect2(416, 0, 32, 16), new Vector2I(RiverX + 1, 30), false); // moored boat
    }

    private void PaintFields(int x0, int y0, int w, int h)
    {
        for (int px = x0; px < x0 + w; px += 5)
            for (int py = y0; py < y0 + h; py += 4)
                for (int x = 0; x < 4; x++)
                    for (int y = 0; y < 3; y++)
                    {
                        int ax = x == 0 ? 0 : x == 3 ? 2 : 1;
                        int ay = 6 + (y == 0 ? 0 : y == 2 ? 2 : 1);
                        var c = new Vector2I(px + x, py + y);
                        if (c.X >= W || c.Y >= H) continue;
                        SetTile(_field, c, new Vector2I(ax, ay));
                        _reserved[c.X, c.Y] = true;
                    }
    }

    // ---------------------------------------------------------------- buildings

    private record Building(string Place, string Png, Rect2 Region, int OffsetX = 0);

    private static readonly Building[] Buildings =
    {
        new("bakery", "tiles/house.png", new Rect2(256, 0, 48, 48)),
        new("teahouse", "tiles/house.png", new Rect2(304, 0, 64, 48)),
        new("forge", "tiles/house.png", new Rect2(368, 0, 48, 48)),
        new("shrine", "tiles/house.png", new Rect2(192, 0, 64, 48)),
        new("dojo", "tiles/house.png", new Rect2(400, 224, 64, 80)),
        new("house_haru", "tiles/house.png", new Rect2(464, 0, 64, 64)),
        new("house_mira", "tiles/house.png", new Rect2(0, 0, 64, 48)),
        new("house_goro", "tiles/house.png", new Rect2(64, 0, 64, 48)),
        new("house_farm", "tiles/house.png", new Rect2(128, 0, 64, 48)),
        new("house_sen", "tiles/house.png", new Rect2(48, 128, 48, 32)),
    };

    private void PlaceBuildings(World world)
    {
        foreach (var b in Buildings)
        {
            var place = world.FindPlace(b.Place);
            if (place == null) continue;
            int doorX = (int)place.Position.X + b.OffsetX;
            int bottom = (int)place.Position.Y - 2;
            Prop(b.Png, b.Region, new Vector2I(doorX, bottom), true);
            Doors[b.Place] = CellCenter(new Vector2I(doorX, bottom + 1));
            Lanterns.Add(CellCenter(new Vector2I(doorX, bottom)) + new Vector2(0, -4));
            int wTiles = Mathf.CeilToInt(b.Region.Size.X / T), hTiles = Mathf.CeilToInt(b.Region.Size.Y / T);
            int left = doorX - wTiles / 2;
            for (int x = left - 1; x <= left + wTiles; x++)
                for (int y = bottom - hTiles; y <= bottom + 1; y++)
                    if (x >= 0 && y >= 0 && x < W && y < H) _reserved[x, y] = true;
        }
        // shrine gate and the fox guardian
        Prop("tiles/house.png", new Rect2(7, 82, 34, 29), new Vector2I(36 + OX, 12), false);
        Prop("tiles/house.png", new Rect2(48, 240, 48, 48), new Vector2I(40 + OX, 8), true);
        Prop("tiles/house.png", new Rect2(64, 64, 32, 16), new Vector2I(48 + OX, 27), false, 1);  // DOJO sign
    }

    /// <summary>A sprite standing on its bottom-centre tile. Solid props block their lower rows.</summary>
    private Sprite2D Prop(string png, Rect2 region, Vector2I baseCell, bool solid, int zBoost = 0)
    {
        var sprite = new Sprite2D
        {
            Texture = Assets.Region(png, region),
            Centered = false,
            Offset = new Vector2(-region.Size.X / 2f, -region.Size.Y),
            Position = new Vector2(baseCell.X * T + T / 2f, (baseCell.Y + 1) * T),
            ZIndex = zBoost,
        };
        Entities.AddChild(sprite);
        if (solid)
        {
            int wTiles = Mathf.Max(1, Mathf.RoundToInt(region.Size.X / T));
            int hTiles = Mathf.Max(1, Mathf.RoundToInt(region.Size.Y / T));
            int left = baseCell.X - wTiles / 2;
            int solidRows = Math.Max(1, hTiles - 1);
            for (int x = left; x < left + wTiles; x++)
                for (int y = baseCell.Y - solidRows + 1; y <= baseCell.Y; y++)
                    if (x >= 0 && y >= 0 && x < W && y < H) { Blocked[x, y] = true; _reserved[x, y] = true; }
        }
        else if (baseCell.X >= 0 && baseCell.Y >= 0 && baseCell.X < W && baseCell.Y < H) _reserved[baseCell.X, baseCell.Y] = true;
        return sprite;
    }

    private void PlaceProps()
    {
        // market stalls and goods around the square
        Prop("tiles/house.png", new Rect2(256, 256, 48, 32), new Vector2I(32 + OX, 18), true);
        Prop("tiles/house.png", new Rect2(304, 256, 48, 32), new Vector2I(40 + OX, 18), true);
        Prop("tiles/house.png", new Rect2(256, 208, 48, 16), new Vector2I(32 + OX, 26), false);
        Prop("tiles/house.png", new Rect2(256, 232, 48, 16), new Vector2I(44 + OX, 14), true);
        // festival banners (hidden until a festival starts)
        int[] bx = { 30 + OX, 33 + OX, 39 + OX, 42 + OX };
        for (int i = 0; i < bx.Length; i++)
        {
            var banner = Prop("tiles/house.png", new Rect2(352 + 16 * (i * 2 % 7), 320, 16, 32), new Vector2I(bx[i], 17), false);
            banner.Visible = false;
            FestivalDecor.Add(banner);
            Lanterns.Add(new Vector2(bx[i] * T + 8, 17 * T));
        }
        // hay by the farm, pots at the tea house
        Prop("tiles/element.png", new Rect2(144, 64, 32, 32), new Vector2I(67 + OX, 29), true);
        Prop("tiles/house.png", new Rect2(256, 176, 48, 32), new Vector2I(21 + OX, 29), true);
        // Crow's camp
        Prop("tiles/camp.png", new Rect2(64, 0, 48, 48), new Vector2I(6, 8), true);
        Prop("tiles/camp.png", new Rect2(112, 0, 48, 48), new Vector2I(13, 8), true);
        Prop("tiles/camp.png", new Rect2(160, 0, 48, 48), new Vector2I(10, 6), true);
        Prop("tiles/camp.png", new Rect2(192, 80, 32, 32), new Vector2I(9, 11), true);
        Prop("tiles/camp.png", new Rect2(128, 48, 32, 32), new Vector2I(5, 12), true);
        Prop("tiles/camp.png", new Rect2(96, 80, 32, 32), new Vector2I(14, 12), true);
        Lanterns.Add(CellCenter(new Vector2I(9, 11)));
        // old stone guardians at the spirit grove
        Prop("tiles/house.png", new Rect2(48, 304, 48, 48), new Vector2I(30, 5), true);
        Prop("tiles/house.png", new Rect2(144, 304, 48, 48), new Vector2I(35, 5), true);
    }

    // ---------------------------------------------------------------- nature

    private static readonly Rect2[] SmallTrees = { new(0, 0, 32, 32), new(32, 0, 32, 32), new(96, 0, 32, 32), new(224, 0, 32, 32), new(256, 0, 32, 32), new(96, 128, 32, 32) };
    private static readonly Rect2[] BigTrees = { new(0, 288, 48, 48), new(48, 288, 48, 48), new(144, 288, 48, 48) };
    private static readonly Rect2[] Clusters = { new(0, 32, 64, 48), new(64, 32, 64, 48), new(192, 32, 64, 48), new(256, 32, 64, 48) };
    private static readonly Rect2[] Flowers = { new(0, 176, 16, 16), new(16, 176, 16, 16), new(32, 176, 16, 16), new(48, 176, 16, 16), new(96, 176, 16, 16), new(0, 160, 16, 16), new(16, 160, 16, 16), new(64, 160, 16, 16) };

    private bool Free(int x, int y, int margin)
    {
        for (int dx = -margin; dx <= margin; dx++)
            for (int dy = -margin; dy <= margin; dy++)
            {
                int cx = x + dx, cy = y + dy;
                if (cx < 0 || cy < 0 || cx >= W || cy >= H) continue;
                if (_reserved[cx, cy]) return false;
            }
        return true;
    }

    private void Tree(Rect2 region, int x, int y)
    {
        var s = Prop("tiles/nature.png", region, new Vector2I(x, y), false);
        int wTiles = Mathf.RoundToInt(region.Size.X / T), hTiles = Mathf.RoundToInt(region.Size.Y / T);
        int half = Math.Max(0, (wTiles - 2) / 2);   // 32 px: the trunk column; 48-64 px: one more on each side
        for (int dx = -half; dx <= half; dx++)
            for (int dy = -1; dy <= 0; dy++) // trunk and lower foliage: you walk around a tree, not into it
            {
                int cx = x + dx, cy = y + dy;
                if (cx >= 0 && cy >= 0 && cx < W && cy < H) Blocked[cx, cy] = true;
            }
        for (int dx = -1; dx <= 1; dx++)
            for (int dy = -1; dy <= 0; dy++)
                if (x + dx >= 0 && x + dx < W && y + dy >= 0) _reserved[x + dx, y + dy] = true;
        s.Scale = new Vector2(_rng.Randf() < 0.5f ? -1 : 1, 1);
    }

    private void PlantForest()
    {
        // dense western forest (the bandits' side), leaving the trail open
        for (int x = 0; x <= RiverX - 2; x += 2)
            for (int y = 1; y < H; y += 2)
            {
                if (_rng.Randf() < 0.8f && Free(x, y, 1))
                    Tree(_rng.Randf() < 0.4f ? SmallTrees[1] : _rng.Randf() < 0.5f ? BigTrees[_rng.RandiRange(0, BigTrees.Length - 1)] : Clusters[_rng.RandiRange(0, 1)], x, y);
            }
        // borders
        for (int x = RiverX + 3; x < W; x += 2)
        {
            if (Free(x, 1, 0)) Tree(SmallTrees[_rng.RandiRange(0, SmallTrees.Length - 1)], x, 1);
            if (Free(x, H - 1, 0)) Tree(SmallTrees[_rng.RandiRange(0, SmallTrees.Length - 1)], x, H - 1);
        }
        for (int y = 3; y < H - 1; y += 2)
            if (Free(W - 2, y, 0)) Tree(SmallTrees[_rng.RandiRange(0, SmallTrees.Length - 1)], W - 2, y);
        // scattered sakura, autumn and green trees
        int placed = 0;
        for (int tries = 0; tries < 2000 && placed < 55; tries++)
        {
            int x = _rng.RandiRange(RiverX + 4, W - 4), y = _rng.RandiRange(3, H - 3);
            if (!Free(x, y, 1)) continue;
            Tree(_rng.Randf() < 0.45f ? BigTrees[_rng.RandiRange(0, BigTrees.Length - 1)] : SmallTrees[_rng.RandiRange(0, SmallTrees.Length - 1)], x, y);
            placed++;
        }
        // flowers and grass tufts (walkable)
        for (int i = 0; i < 260; i++)
        {
            int x = _rng.RandiRange(RiverX + 3, W - 2), y = _rng.RandiRange(2, H - 2);
            if (_reserved[x, y] || Blocked[x, y]) continue;
            var flower = new Sprite2D
            {
                Texture = Assets.Region("tiles/nature.png", Flowers[_rng.RandiRange(0, Flowers.Length - 1)]),
                Position = CellCenter(new Vector2I(x, y)) + new Vector2(_rng.RandfRange(-4, 4), _rng.RandfRange(-4, 4)),
                ZIndex = -1,
            };
            AddChild(flower);
        }
    }

    // ---------------------------------------------------------------- pathfinding

    private void BuildPathfinder()
    {
        for (int x = 0; x < W; x++) Blocked[x, 0] = true;
        Astar.Region = new Rect2I(0, 0, W, H);
        Astar.CellSize = new Vector2(T, T);
        Astar.DiagonalMode = AStarGrid2D.DiagonalModeEnum.OnlyIfNoObstacles;
        Astar.Update();
        for (int x = 0; x < W; x++)
            for (int y = 0; y < H; y++)
                if (Blocked[x, y]) Astar.SetPointSolid(new Vector2I(x, y));
        // dirt is cheaper to walk: characters prefer the roads
        for (int x = 0; x < W; x++)
            for (int y = 0; y < H; y++)
                Astar.SetPointWeightScale(new Vector2I(x, y), _dirt.Contains(new Vector2I(x, y)) ? 1f : 2.5f);
    }

    public bool IsBlocked(Vector2I c) => c.X < 0 || c.Y < 0 || c.X >= W || c.Y >= H || Blocked[c.X, c.Y];

    /// <summary>Nearest walkable cell to a wished-for cell (destinations sometimes fall inside props).</summary>
    public Vector2I NearestFree(Vector2I c)
    {
        c = new Vector2I(Math.Clamp(c.X, 0, W - 1), Math.Clamp(c.Y, 0, H - 1));
        if (!IsBlocked(c)) return c;
        for (int r = 1; r < 8; r++)
            for (int dx = -r; dx <= r; dx++)
                for (int dy = -r; dy <= r; dy++)
                {
                    var n = new Vector2I(c.X + dx, c.Y + dy);
                    if (!IsBlocked(n)) return n;
                }
        return c;
    }

    public List<Vector2> Path(Vector2 from, Vector2 to)
    {
        var a = NearestFree(Cell(from));
        var b = NearestFree(Cell(to));
        var ids = Astar.GetIdPath(a, b);
        var list = new List<Vector2>(ids.Count);
        foreach (var id in ids) list.Add(CellCenter(id));
        if (list.Count > 0) list.RemoveAt(0);
        return list;
    }
}
