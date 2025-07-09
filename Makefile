CODE = .
MESSAGE = "No such command (or you pass two or many targets to ). List of possible commands: make help"
HELP_FUN = \
	%help; while(<>){push@{$$help{$$2//'options'}},[$$1,$$3] \
	if/^([\w-_]+)\s*:.*\#\#(?:@(\w+))?\s(.*)$$/}; \
    print"$$_:\n", map"  $$_->[0]".(" "x(20-length($$_->[0])))."$$_->[1]\n",\
    @{$$help{$$_}},"\n" for keys %help;

help: ##@Help Show this help
	@echo -e "Usage: make [target] ...\n"
	@perl -e '$(HELP_FUN)' $(MAKEFILE_LIST)


format: ##@Code Format code with ruff
	ruff format $(CODE)

lint: ##@Code Check code with ruff (alias for check)
	ruff check --fix $(CODE)

%::
	echo $(MESSAGE)

run:  ##@Application Run application server
	docker compose up --build -d

