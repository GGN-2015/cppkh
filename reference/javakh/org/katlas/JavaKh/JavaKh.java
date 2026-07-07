package org.katlas.JavaKh;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileReader;
import java.io.IOException;
import java.io.StringReader;
import java.text.DecimalFormat;
import java.util.ArrayList;
import java.util.List;

import org.apache.commons.cli.CommandLine;
import org.apache.commons.cli.CommandLineParser;
import org.apache.commons.cli.HelpFormatter;
import org.apache.commons.cli.Options;
import org.apache.commons.cli.PosixParser;
import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.apache.log4j.Level;
import org.apache.log4j.Logger;
import org.katlas.JavaKh.algebra.rings.ModP;
import org.katlas.JavaKh.algebra.rings.Rings;

public class JavaKh {
    private static final Log log = LogFactory.getLog(JavaKh.class);

    public static boolean using_h = false;
    public static boolean inMemory = true;

    public static void main(String[] args) throws IOException {
        boolean reorderCrossings = true;
        boolean useDiskCache = true;
        String inputPath = "PD.txt";

        try {
            CommandLineParser parser = new PosixParser();
            Options options = createOptions();
            CommandLine commandLine = parser.parse(options, args);
            configureLogging(commandLine);
            configureRing(commandLine);

            if (commandLine.hasOption("U")) {
                using_h = true;
            }
            if (commandLine.hasOption("O")) {
                reorderCrossings = false;
            }
            if (commandLine.hasOption("C")) {
                useDiskCache = true;
            }
            if (commandLine.hasOption("D")) {
                inMemory = false;
            }
            if (commandLine.hasOption("N")) {
                CannedCobordismImpl.disableCache();
            }
            if (commandLine.hasOption("P")) {
                Komplex.parallel = true;
            }
            if (commandLine.hasOption("G")) {
                Komplex.intenseGarbage = true;
            }
            if (commandLine.hasOption("f")) {
                inputPath = commandLine.getOptionValue("f");
            } else if (commandLine.getArgs().length > 0) {
                inputPath = commandLine.getArgs()[0];
            }
            if (commandLine.hasOption("h")) {
                HelpFormatter formatter = new HelpFormatter();
                formatter.printHelp("Usage: java JavaKh [OPTIONS] [PD_FILE]", options);
                System.exit(1);
            }
        } catch (Exception e) {
            log.fatal("Error found initializing", e);
            System.exit(1);
        }

        long startedAt = System.currentTimeMillis();
        List<String> pdLines = readPDLines(new File(inputPath));
        for (int i = 0; i < pdLines.size(); ++i) {
            String line = pdLines.get(i);
            try {
                if (useDiskCache) {
                    clearCacheDirectory();
                }
                int[][] pd = Komplex.getPD(new BufferedReader(new StringReader(line)));
                if (pd == null) {
                    throw new IllegalArgumentException("could not parse PD code");
                }
                Komplex<?> komplex = Komplex.generateFast(
                    pd,
                    Komplex.getSigns(pd),
                    reorderCrossings,
                    useDiskCache,
                    inMemory
                );
                assert komplex.check(true);
                log.info("Elapsed time:" + new DecimalFormat("###,###,###,###").format(System.currentTimeMillis() - startedAt));
                startedAt = System.currentTimeMillis();
                System.out.println("\"" + komplex.Kh() + "\"");
            } catch (Throwable error) {
                System.out.println(formatPDLineError(i + 1, line, error));
                startedAt = System.currentTimeMillis();
                if (useDiskCache) {
                    clearCacheDirectory();
                }
                System.gc();
            }
        }
    }

    private static Options createOptions() {
        Options options = new Options();
        options.addOption("h", "help", false, "show this help screen");
        options.addOption("i", "info", false, "turn on lower level debugging statements [INFO].");
        options.addOption("d", "debug", false, "turn on lowest level debugging statements [DEBUG].");
        options.addOption("U", "universal", false, "use the universal theory over the integers");
        options.addOption("Z", "integer", false, "work over the integers");
        options.addOption("Q", "rational", false, "work over the rationals");
        options.addOption("m", "mod", true, "work over a field of characteristic p");
        options.addOption("f", "pd-file", true, "read PD codes from file (default: PD.txt)");
        options.addOption("O", "ordered", false, "don't change the ordering of the crossings");
        options.addOption("C", "caching", false, "cache intermediate steps to the cache/ directory");
        options.addOption("D", "disk", false, "store large lists on disk, rather than in memory (slow!)");
        options.addOption("N", "nocobordisms", false, "disable the cobordism cache");
        options.addOption("P", "parallel", false, "simplify complexes using parallel threads (experimental)");
        options.addOption("G", "garbage", false, "perform intense garbage collection");
        return options;
    }

    private static void configureLogging(CommandLine commandLine) {
        Logger root = Logger.getRootLogger();
        if (commandLine.hasOption("d")) {
            root.setLevel(Level.DEBUG);
        } else if (commandLine.hasOption("i")) {
            root.setLevel(Level.INFO);
        } else {
            root.setLevel(Level.WARN);
        }
    }

    private static void configureRing(CommandLine commandLine) {
        if (commandLine.hasOption("Z")) {
            Rings.setRing("Int");
        } else if (commandLine.hasOption("Q")) {
            Rings.setRing("Rational");
        } else if (commandLine.hasOption("m")) {
            int p = Integer.parseInt(commandLine.getOptionValue("m"));
            if (p == 0) {
                Rings.setRing("Rational");
            } else {
                ModP.setP(p);
                Rings.setRing("ModP");
            }
        } else {
            Rings.setRing("Int");
        }
    }

    private static List<String> readPDLines(File file) throws IOException {
        List<String> lines = new ArrayList<String>();
        BufferedReader reader = new BufferedReader(new FileReader(file));
        try {
            String line;
            while ((line = reader.readLine()) != null) {
                line = line.trim();
                if (line.length() != 0) {
                    lines.add(line);
                }
            }
        } finally {
            reader.close();
        }
        return lines;
    }

    private static String formatPDLineError(int lineNumber, String pdCode, Throwable error) {
        String message = error.getClass().getName();
        if (error.getMessage() != null && error.getMessage().length() != 0) {
            message = message + ": " + error.getMessage();
        }
        return "ERROR line=" + lineNumber + " pd=" + singleLine(pdCode) + " error=" + singleLine(message);
    }

    private static String singleLine(String text) {
        return text.replace('\r', ' ').replace('\n', ' ').replace('\t', ' ').trim();
    }

    private static void clearCacheDirectory() {
        deleteRecursively(new File("cache"));
    }

    private static void deleteRecursively(File file) {
        if (!file.exists()) {
            return;
        }
        if (file.isDirectory()) {
            File[] children = file.listFiles();
            if (children != null) {
                for (int i = 0; i < children.length; ++i) {
                    deleteRecursively(children[i]);
                }
            }
        }
        file.delete();
    }
}
