all: main.py values.py
clean:
	rm -f *.py

%.py: %.ui
	pyuic5 -x $< -o $@
