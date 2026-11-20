.DEFAULT_GOAL := all

ifeq ($(strip $(PSL1GHT)),)
$(error Set PSL1GHT to the installed PSL1GHT directory)
endif

include $(PSL1GHT)/ppu_rules

TITLE := PS3 Stats
APPID := ZSTATS001
CONTENTID := UP0001-$(APPID)_00-0000000000000000
ICON0 := $(CURDIR)/ICON0.PNG
SFOXML := $(CURDIR)/param.xml
CFLAGS := -O2 -Wall -Wextra -std=gnu99 -mcpu=cell $(MACHDEP) $(LIBPSL1GHT_INC)
LIBPATHS := $(LIBPSL1GHT_LIB)
LIBS := -lrsx -lgcm_sys -lio -lsysutil -lrt -llv2
LDFLAGS := $(MACHDEP)
LD := $(CC)

.PHONY: all clean
all: PS3_Stats.pkg

PS3_Stats.elf: build/main.o
PS3_Stats.pkg: ICON0.PNG param.xml

build/main.o: source/main.c source/font.h
	mkdir -p build
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -rf build PS3_Stats.elf PS3_Stats.self PS3_Stats.fake.self PS3_Stats.pkg PS3_Stats.gnpdrm.pkg
