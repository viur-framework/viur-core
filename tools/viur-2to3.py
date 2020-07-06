#!/usr/bin/python3
"""
Naive ViUR3 project porting script with a simple search & replace mechanism using lookup table.
"""

import os, argparse, sys

# Naive lookup table. Could be done better later...
lookup = {
	"onItemAdded": "onAdded",
	"onItemEdited": "onEdited",
	"onItemDeleted": "onDeleted",
	"addItemSuccess": "addSuccess",
	"editItemSuccess": "editSuccess"
}

if __name__ == "__main__":
	# Get arguments
	ap = argparse.ArgumentParser(
		description="naive ViUR2-to-ViUR3 porting tool"
	)

	ap.add_argument(
		"project_root",
		type=str,
		help="ViUR project root"
	)

	ap.add_argument(
		"-d", "--dryrun",
		action="store_true",
		help="Dry-run for testing, don't modify files"
	)
	ap.add_argument(
		"-x", "--daredevil",
		action="store_true",
		help="Don't make backups of files, just replace and deal with it"
	)

	args = ap.parse_args()

	# Iterate all files in current folder
	for root, dirs, files in os.walk(args.project_root):
		# Ignore ViUR library folders
		if any(ignore in root for ignore in ["viur", "html5"]):
			continue

		for filename in files:
			# Ignore anywhing without a .py-extension
			ext = os.path.splitext(filename)[1].lower()[1:]
			if ext not in ["py"]:
				continue

			filename = os.path.join(root, filename)

			with open(filename, "r") as f:
				content = f.read()

			count = 0
			for k, v in lookup.items():
				if k in content:
					content = content.replace(k, v)
					count += 1

			if count:
				if not args.daredevil:
					os.rename(filename, filename + ".bak")

				if not args.dryrun:
					with open(filename, "w") as f:
						f.write(content)

				print("Modified %r" % filename)
