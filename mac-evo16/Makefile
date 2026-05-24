# Makefile for mac-evo16 — macOS IOKit USB helper
CC     = cc
CFLAGS = -Wall -O2
LIBS   = -framework IOKit -framework CoreFoundation
NAME   = mac-evo16

all: $(NAME)

$(NAME): $(NAME).c
	$(CC) $(CFLAGS) -o $(NAME) $(NAME).c $(LIBS)

clean:
	rm -f $(NAME)

install: $(NAME)
	sudo cp $(NAME) /usr/local/libexec/
	sudo chown root:wheel /usr/local/libexec/$(NAME)
	sudo chmod u+s /usr/local/libexec/$(NAME)
	@echo "Installed $(NAME) with setuid root"

uninstall:
	sudo rm -f /usr/local/libexec/$(NAME)
	@echo "Removed $(NAME)"
