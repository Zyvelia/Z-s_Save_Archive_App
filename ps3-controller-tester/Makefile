.DEFAULT_GOAL := all

ifeq ($(strip $(PSL1GHT)),)
$(error Set PSL1GHT to the installed PSL1GHT directory)
endif

include $(PSL1GHT)/ppu_rules

TITLE := Controller Tester
APPID := ZPADT0001
CONTENTID := UP0001-$(APPID)_00-0000000000000000
ICON0 := $(CURDIR)/ICON0.PNG
SFOXML := $(CURDIR)/param.xml
CFLAGS := -O2 -Wall -Wextra -std=gnu99 -mcpu=cell $(MACHDEP) $(LIBPSL1GHT_INC)
LIBPATHS := $(LIBPSL1GHT_LIB)
LIBS := -lrsx -lgcm_sys -lio -lsysutil -lrt -llv2
LDFLAGS := $(MACHDEP)
LD := $(CC)

.PHONY: all clean
all: Controller_Tester.pkg

Controller_Tester.elf: build/main.o
Controller_Tester.pkg: ICON0.PNG param.xml

build/main.o: source/main.c source/dashboard.h ../ps3-stats/source/font.h
	mkdir -p build
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -rf build Controller_Tester.elf Controller_Tester.self Controller_Tester.fake.self Controller_Tester.pkg Controller_Tester.gnpdrm.pkg
