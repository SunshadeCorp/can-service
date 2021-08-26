all: main.py
clean:
	rm -f *.py

%.py: %.ui
	pyuic5 -x $< -o $@
