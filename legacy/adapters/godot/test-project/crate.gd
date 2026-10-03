extends Node2D
# A plain GDScript node: Kinloom reads, writes and calls its members by name.
@export var weight := 2.5
var color_name := "red"
var pushed_with := 0.0

func push(force: float) -> void:
	pushed_with = force
