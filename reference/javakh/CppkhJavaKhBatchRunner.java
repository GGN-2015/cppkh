import java.io.File;
import java.io.PrintStream;
import java.lang.reflect.Method;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public final class CppkhJavaKhBatchRunner {
    private CppkhJavaKhBatchRunner() {}

    public static void main(String[] args) throws Exception {
        if (args.length < 1 || args.length > 2) {
            throw new IllegalArgumentException("usage: CppkhJavaKhBatchRunner <prepared-pd-file> [--keep-cache]");
        }

        Path input = Paths.get(args[0]).toAbsolutePath();
        boolean keepCache = args.length == 2 && "--keep-cache".equals(args[1]);
        List<String> lines = Files.readAllLines(input, StandardCharsets.UTF_8);
        Path pdFile = Paths.get("PD.txt");
        PrintStream originalOut = System.out;
        PrintStream originalErr = System.err;
        URL[] classPath = currentClassPathUrls();

        int index = 0;
        for (String raw : lines) {
            String line = raw.trim();
            if (line.isEmpty()) {
                continue;
            }
            ++index;
            Files.write(pdFile, (line + System.lineSeparator()).getBytes(StandardCharsets.UTF_8));
            if (!keepCache) {
                deleteRecursively(Paths.get("cache"));
            }
            URLClassLoader loader = new URLClassLoader(classPath, null);
            ClassLoader oldContextLoader = Thread.currentThread().getContextClassLoader();
            try {
                Thread.currentThread().setContextClassLoader(loader);
                Class<?> mainClass = Class.forName("org.katlas.JavaKh.JavaKh", true, loader);
                Method main = mainClass.getMethod("main", String[].class);
                main.invoke(null, (Object) new String[0]);
            } catch (Throwable t) {
                System.setOut(originalOut);
                System.setErr(originalErr);
                originalErr.println("JavaKh failed at batch item " + index + ": " + line);
                t.printStackTrace(originalErr);
                System.exit(1);
            } finally {
                Thread.currentThread().setContextClassLoader(oldContextLoader);
                loader.close();
                System.setOut(originalOut);
                System.setErr(originalErr);
            }
        }
    }

    private static URL[] currentClassPathUrls() throws Exception {
        String[] entries = System.getProperty("java.class.path").split(File.pathSeparator);
        ArrayList<URL> urls = new ArrayList<URL>();
        for (String entry : entries) {
            if (entry == null || entry.length() == 0) {
                continue;
            }
            urls.add(new File(entry).toURI().toURL());
        }
        return urls.toArray(new URL[urls.size()]);
    }

    private static void deleteRecursively(Path root) throws Exception {
        if (!Files.exists(root)) {
            return;
        }
        Files.walk(root)
            .sorted(Comparator.reverseOrder())
            .forEach(path -> {
                try {
                    Files.deleteIfExists(path);
                } catch (Exception e) {
                    throw new RuntimeException(e);
                }
            });
    }
}
