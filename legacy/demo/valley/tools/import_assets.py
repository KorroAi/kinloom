"""Copies the subset of the Ninja Adventure asset pack (CC0, by Pixel-Boy and AAA) that Asagiri Valley uses.

Usage: python tools/import_assets.py <path to 'Ninja Adventure - Asset Pack'> <path to pixel-boy/NinjaAdventure repo>
Download: https://pixel-boy.itch.io/ninja-adventure-asset-pack  and  https://github.com/pixel-boy/NinjaAdventure
"""
import shutil
import sys
from pathlib import Path

LOOKS = ["Hunter", "OldMan", "Samurai", "SamuraiBlue", "Princess", "Villager2", "SorcererOrange", "Villager",
         "Villager4", "OldWoman", "Monk", "Villager5", "Cavegirl", "Sultan", "SamuraiRed", "NinjaDark", "NinjaRed2", "MaskRacoon",
         "NinjaGray", "NinjaRed", "Slime", "SpiderRed", "Beast", "Skull", "Mushroom"]

FILES = {
    "Backgrounds/Tilesets/TilesetHouse.png": "tiles/house.png",
    "Backgrounds/Tilesets/TilesetNature.png": "tiles/nature.png",
    "Backgrounds/Tilesets/TilesetWater.png": "tiles/water.png",
    "Backgrounds/Tilesets/TilesetElement.png": "tiles/element.png",
    "Backgrounds/Tilesets/TilesetFloorDetail.png": "tiles/floor_detail.png",
    "Backgrounds/Tilesets/TilesetField.png": "tiles/field.png",
    "Actor/Character/Shadow.png": "chars/shadow.png",
    "Ui/Font/NormalFont.ttf": "ui/NormalFont.ttf",
    "Ui/Dialog/DialogBoxFaceset.png": "ui/dialog_faceset.png",
    "Ui/Dialog/FacesetBox.png": "ui/faceset_box.png",
    "Ui/Dialog/ChoiceBox.png": "ui/choice_box.png",
    "Ui/Receptacle/Heart.png": "ui/heart.png",
    "FX/Slash/SpriteSheetSlash01.png": "fx/slash.png",
    "FX/Smoke/Smoke/SpriteSheet.png": "fx/smoke.png",
    "FX/Particle/Rain.png": "fx/rain.png",
    "FX/Particle/Leaf.png": "fx/leaf.png",
    "FX/Particle/LeafPink.png": "fx/leaf_pink.png",
    "FX/Particle/Spark.png": "fx/spark.png",
    "FX/Environment/Fog.png": "fx/fog.png",
    "Items/Treasure/GoldCoin.png": "items/coin.png",
    "Items/Treasure/LittleTreasureChest.png": "items/chest.png",
    "Items/Scroll/Scroll.png": "items/scroll.png",
    "Items/Scroll/ScrollEmpty.png": "items/letter.png",
    "Items/Food/Onigiri.png": "items/buns.png",
    "Items/Food/TeaLeaf.png": "items/herbs.png",
    "Items/Object/Gourd.png": "items/sake.png",
    "Items/Object/Bag.png": "items/silk.png",
    "Items/Object/Dice 6.png": "items/dice.png",
    "Items/Treasure/GoldCup.png": "items/relic.png",
    "Items/Treasure/SilverKey.png": "items/comb.png",
    "Items/Weapons/Katana/Sprite.png": "items/katana.png",
    "Backgrounds/Tilesets/tileset_camp.png": "tiles/camp.png",
    "Items/Resource/Rock.png": "items/ore.png",
    "Items/Resource/Grass.png": "items/moon_herb.png",
    "Items/Resource/GemGreen.png": "items/gem.png",
    "Items/Potion/LifePot.png": "items/potion.png",
    "Audio/Musics/4 - Village.ogg": "audio/music_day.ogg",
    "Audio/Musics/33 - Calm Village.ogg": "audio/music_morning.ogg",
    "Audio/Musics/9 - Quiet.ogg": "audio/music_night.ogg",
    "Audio/Musics/28 - Tension.ogg": "audio/music_tension.ogg",
    "Audio/Musics/17 - Fight.ogg": "audio/music_fight.ogg",
    "Audio/Musics/20 - Good Time.ogg": "audio/music_festival.ogg",
    "Audio/Musics/7 - Sad Theme.ogg": "audio/music_sad.ogg",
    "Audio/Musics/38 - Intro.ogg": "audio/music_title.ogg",
    "Audio/Sounds/Whoosh & Slash/Slash.wav": "audio/slash.wav",
    "Audio/Sounds/Hit & Impact/Hit1.wav": "audio/hit.wav",
    "Audio/Sounds/Hit & Impact/Impact.wav": "audio/impact.wav",
    "Audio/Sounds/Whoosh & Slash/Whoosh.wav": "audio/dash.wav",
    "Audio/Sounds/Alert/Alert2.wav": "audio/alert.wav",
    "Audio/Sounds/Menu/Accept.wav": "audio/accept.wav",
    "Audio/Sounds/Menu/Menu5.wav": "audio/menu.wav",
    "Audio/Sounds/Menu/Cancel.wav": "audio/cancel.wav",
    "Audio/Sounds/Bonus/Coin.wav": "audio/coin.wav",
    "Audio/Sounds/Ambient/Rain.wav": "audio/rain.wav",
    "Audio/Sounds/Ambient/River.wav": "audio/river.wav",
    "Audio/Sounds/Creature/Bird.wav": "audio/bird.wav",
    "Audio/Sounds/Magic & Skill/Spirit.wav": "audio/thought.wav",
    "Audio/Jingles/Success2.wav": "audio/quest_done.wav",
    "Audio/Jingles/Secret2.wav": "audio/quest_new.wav",
    "Audio/Jingles/GameOver.wav": "audio/death.wav",
    "Audio/Jingles/LevelUp1.wav": "audio/event.wav",
}


def main(pack: Path, repo: Path, out: Path) -> None:
    def copy(src: Path, dst: Path) -> None:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)

    for look in LOOKS:
        src = pack / "Actor/Character" / look
        if not src.exists():
            src = pack / "Actor/Monster" / look
        sheet = src / "SpriteSheet.png"
        if not sheet.exists():  # a few characters name their sheet differently
            sheet = next(f for f in src.glob("*.png") if f.name != "Faceset.png")
        copy(sheet, out / "chars" / look / "SpriteSheet.png")
        copy(src / "Faceset.png", out / "chars" / look / "Faceset.png")
    for i in range(1, 31):
        copy(pack / f"Ui/Emote/emote{i}.png", out / f"ui/emote/emote{i}.png")
    for i in range(1, 11):
        copy(pack / f"Audio/Sounds/Voice/Voice{i}.wav", out / f"audio/voice{i}.wav")
    for f in (pack / "Ui/Theme/Theme Wood").glob("*.png"):
        copy(f, out / "ui/theme" / f.name)
    for src, dst in FILES.items():
        copy(pack / src, out / dst)
    copy(repo / "content/map/tileset_floor.png", out / "tiles/tileset_floor.png")
    # floor.tres (grass/dirt terrains) is extracted from the repo's tileset.tres by tools/extract_floor_tileset.py


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), Path(__file__).resolve().parent.parent / "assets")
    print("assets imported")
