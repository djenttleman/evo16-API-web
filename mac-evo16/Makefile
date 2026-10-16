# Makefile for mac-evo16 — macOS IOKit USB helper
CC     = cc
MACOSX_DEPLOYMENT_TARGET ?= 13.0
CFLAGS = -Wall -O2 -mmacosx-version-min=$(MACOSX_DEPLOYMENT_TARGET)
LIBS   = -framework IOKit -framework CoreFoundation
NAME   = mac-evo16

all: $(NAME)

$(NAME): $(NAME).c Makefile
	$(CC) $(CFLAGS) -o $(NAME) $(NAME).c $(LIBS)

clean:
	rm -f $(NAME)

PREFIX ?= $(HOME)/.local

install: $(NAME)
	mkdir -p "$(PREFIX)/libexec"
	install -m 755 $(NAME) "$(PREFIX)/libexec/$(NAME)"
	@echo "Installed $(NAME) without elevated privileges"

uninstall:
	rm -f "$(PREFIX)/libexec/$(NAME)"
