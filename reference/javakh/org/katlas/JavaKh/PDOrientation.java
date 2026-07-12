package org.katlas.JavaKh;

import java.util.Arrays;

/** Crossing orientations for SageMath-style planar diagram codes. */
public final class PDOrientation {
    private PDOrientation() {}

    public static int[] getSigns(int[][] pd) {
        int nodeCount = pd.length * 4;
        if (nodeCount == 0) {
            return new int[0];
        }

        int maxLabel = -1;
        for (int i = 0; i < pd.length; ++i) {
            if (pd[i].length != 4) {
                throw new IllegalArgumentException("PD crossing must have four entries");
            }
            for (int slot = 0; slot < 4; ++slot) {
                if (pd[i][slot] < 0) {
                    throw new IllegalArgumentException("PD arc labels must be positive");
                }
                maxLabel = Math.max(maxLabel, pd[i][slot]);
            }
        }

        int[] first = new int[maxLabel + 1];
        int[] second = new int[maxLabel + 1];
        Arrays.fill(first, -1);
        Arrays.fill(second, -1);
        for (int i = 0; i < pd.length; ++i) {
            for (int slot = 0; slot < 4; ++slot) {
                int label = pd[i][slot];
                int node = 4 * i + slot;
                if (first[label] == -1) {
                    first[label] = node;
                } else if (second[label] == -1) {
                    second[label] = node;
                } else {
                    throw new IllegalArgumentException("PD arc label appears more than twice");
                }
            }
        }

        int[] other = new int[nodeCount];
        Arrays.fill(other, -1);
        for (int label = 0; label <= maxLabel; ++label) {
            if (first[label] == -1) {
                continue;
            }
            if (second[label] == -1) {
                throw new IllegalArgumentException("PD arc label does not appear twice");
            }
            other[first[label]] = second[label];
            other[second[label]] = first[label];
        }

        byte[] outgoing = new byte[nodeCount];
        Arrays.fill(outgoing, (byte) -1);
        int[] queue = new int[nodeCount];

        for (int i = 0; i < pd.length; ++i) {
            orientComponent(4 * i + 2, (byte) 1, other, outgoing, queue);
        }
        for (int label = 0; label <= maxLabel; ++label) {
            if (first[label] != -1 && outgoing[first[label]] == -1) {
                orientComponent(first[label], (byte) 1, other, outgoing, queue);
            }
        }

        int[] signs = new int[pd.length];
        for (int i = 0; i < pd.length; ++i) {
            int[] crossing = pd[i];
            if (crossing[0] == crossing[3] || crossing[2] == crossing[1]) {
                signs[i] = -1;
            } else if (crossing[3] == crossing[2] || crossing[0] == crossing[1]) {
                signs[i] = 1;
            } else {
                signs[i] = outgoing[4 * i + 3] == 1 ? -1 : 1;
            }
        }
        return signs;
    }

    public static String formatSigns(int[] signs) {
        StringBuilder out = new StringBuilder();
        out.append('[');
        for (int i = 0; i < signs.length; ++i) {
            if (i != 0) {
                out.append(',');
            }
            out.append(signs[i]);
        }
        out.append(']');
        return out.toString();
    }

    private static void orientComponent(
        int seed,
        byte direction,
        int[] other,
        byte[] outgoing,
        int[] queue
    ) {
        if (outgoing[seed] != -1) {
            if (outgoing[seed] != direction) {
                throw new IllegalArgumentException("inconsistent PD orientation");
            }
            return;
        }

        int head = 0;
        int tail = 0;
        outgoing[seed] = direction;
        queue[tail++] = seed;
        while (head < tail) {
            int node = queue[head++];
            int crossing = node / 4;
            int slot = node % 4;
            int opposite = 4 * crossing + ((slot + 2) % 4);
            tail = orientNeighbor(node, opposite, outgoing, queue, tail);
            if (other[node] < 0) {
                throw new IllegalArgumentException("broken PD edge incidence");
            }
            tail = orientNeighbor(node, other[node], outgoing, queue, tail);
        }
    }

    private static int orientNeighbor(
        int node,
        int next,
        byte[] outgoing,
        int[] queue,
        int tail
    ) {
        byte nextDirection = (byte) (1 - outgoing[node]);
        if (outgoing[next] == -1) {
            outgoing[next] = nextDirection;
            queue[tail++] = next;
        } else if (outgoing[next] != nextDirection) {
            throw new IllegalArgumentException("inconsistent PD orientation");
        }
        return tail;
    }
}
