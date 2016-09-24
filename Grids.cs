/********************************************************************** 
 * The following is the code of some classes useful to implement      *
 * grids for turn based or RTS games. Along with the imlementation    *
 * of the grid coordinate system itself there are also some utilities *
 * for path finding and other AI stuff.                               *
 *                                                                    *
 * NOTE: there may be some bug here and there in the code since I had *
 * to rework it to extrapolate it from the actual project on which I  *
 * originally developed it. I hope to find the time soon to give it a *
 * more extensive check and maybe add the hex grid implementation     *
 * (see below).                                                       * 
 **********************************************************************/
 
using System.Collections;
using System.Collections.Generic;
using UnityEngine;

using Exception = System.Exception;
using ArgumentException = System.ArgumentException;
using ArgumentNullException = System.ArgumentException;
using NotImplementedException = System.NotImplementedException;
using InvalidOperationException = System.InvalidOperationException;

namespace Grids
{
	using Quad = Tiles.Quad;
	using AStarSearchQuad = Utils.AStarSearch<Tiles.Quad>;

	namespace Utils
	{
		/* Heap based priority queue, needed by the AStarSearch implementation (see below) */
		public class PriorityQueue<TPriority, TValue> : ICollection<KeyValuePair<TPriority, TValue>>
		{
			List<KeyValuePair<TPriority, TValue>> baseHeap;
			IComparer<TPriority> comparer;

			public PriorityQueue() : this(Comparer<TPriority>.Default) { }

			public PriorityQueue(IComparer<TPriority> comparer)
			{
				if (comparer == null) { throw new ArgumentNullException(); }

				baseHeap = new List<KeyValuePair<TPriority, TValue>>();
				this.comparer = comparer;
			}

			public bool IsEmpty
			{
				get { return baseHeap.Count == 0; }
			}

			public void Enqueue(TPriority priority, TValue value)
			{
				Insert(priority, value);
			}

			public TValue DequeueValue()
			{
				return Dequeue().Value;
			}

			public KeyValuePair<TPriority, TValue> Dequeue()
			{
				if (!IsEmpty)
				{
					KeyValuePair<TPriority, TValue> result = baseHeap[0];
					DeleteRoot();
					return result;
				}
				else
				{
					throw new InvalidOperationException("Priority queue is empty");
				}
			}

			public KeyValuePair<TPriority, TValue> Peek()
			{
				if (!IsEmpty)
				{
					return baseHeap[0];
				}
				else
				{
					throw new InvalidOperationException("Priority queue is empty");
				}
			}

			public TValue PeekValue()
			{
				return Peek().Value;
			}

			// ICollection implementation

			public void Add(KeyValuePair<TPriority, TValue> item)
			{
				Enqueue(item.Key, item.Value);
			}

			public void Clear()
			{
				baseHeap.Clear();
			}

			public bool Contains(KeyValuePair<TPriority, TValue> item)
			{
				return baseHeap.Contains(item);
			}

			public int Count
			{
				get { return baseHeap.Count; }
			}

			public void CopyTo(KeyValuePair<TPriority, TValue>[] array, int arrayIndex)
			{
				baseHeap.CopyTo(array, arrayIndex);
			}

			public bool IsReadOnly
			{
				get { return false; }
			}

			public bool Remove(KeyValuePair<TPriority, TValue> item)
			{
				// find element in the collection and remove it
				int elementIdx = baseHeap.IndexOf(item);
				if (elementIdx < 0) { return false; }

				//remove element
				baseHeap[elementIdx] = baseHeap[baseHeap.Count - 1];
				baseHeap.RemoveAt(baseHeap.Count - 1);

				// heapify
				int newPos = HeapifyFromEndToBeginning(elementIdx);
				if (newPos == elementIdx)
				{
					HeapifyFromBeginningToEnd(elementIdx);
				}

				return true;
			}

			public IEnumerator<KeyValuePair<TPriority, TValue>> GetEnumerator()
			{
				return baseHeap.GetEnumerator();
			}

			
			// Returned enumerator does not iterate elements in sorted order!
			IEnumerator IEnumerable.GetEnumerator()
			{
				return this.GetEnumerator();
			}

			// End of ICollection implementation

			void Insert(TPriority priority, TValue value)
			{
				KeyValuePair<TPriority, TValue> valuePair = new KeyValuePair<TPriority, TValue>(priority, value);
				baseHeap.Add(valuePair);

				// heapify after insert, from end to beginning
				HeapifyFromEndToBeginning(baseHeap.Count - 1);
			}

			int HeapifyFromEndToBeginning(int pos)
			{
				if (pos >= baseHeap.Count) { return -1; }

				// heap[i] have children heap[2*i + 1] and heap[2*i + 2] and parent heap[(i-1)/ 2];

				while (pos > 0)
				{
					int parentPos = (pos - 1) / 2;
					if (comparer.Compare(baseHeap[parentPos].Key, baseHeap[pos].Key) > 0)
					{
						SwapElements(parentPos, pos);
						pos = parentPos;
					}
					else
					{
						break;
					}
				}
				return pos;
			}

			void SwapElements(int a, int b)
			{
				KeyValuePair<TPriority, TValue> valuePair = baseHeap[a];
				baseHeap[a] = baseHeap[b];
				baseHeap[b] = valuePair;
			}

			void DeleteRoot()
			{
				if (baseHeap.Count <= 1)
				{
					baseHeap.Clear();
					return;
				}

				baseHeap[0] = baseHeap[baseHeap.Count - 1];
				baseHeap.RemoveAt(baseHeap.Count - 1);

				// heapify
				HeapifyFromBeginningToEnd(0);
			}

			void HeapifyFromBeginningToEnd(int pos)
			{
				if (pos >= baseHeap.Count) { return; }

				// heap[i] have children heap[2*i + 1] and heap[2*i + 2] and parent heap[(i-1)/ 2];

				while (true)
				{
					// on each iteration exchange element with its smallest child
					int smallest = pos;
					int left = 2 * pos + 1;
					int right = 2 * pos + 2;
					if (left < baseHeap.Count && comparer.Compare(baseHeap[smallest].Key, baseHeap[left].Key) > 0)
					{
						smallest = left;
					}
					if (right < baseHeap.Count && comparer.Compare(baseHeap[smallest].Key, baseHeap[right].Key) > 0)
					{
						smallest = right;
					}

					if (smallest != pos)
					{
						SwapElements(smallest, pos);
						pos = smallest;
					}
					else
					{
						break;
					}
				}
			}
		}

		/********************************************************************************** 
		 * Generic AStarSearch alogirithm on the tiles of a grid. Useful for pathfinding. *
		 * It can be customized with user specified heuristic function, cost function     *
		 * and neighbor function.                                                         *
		 **********************************************************************************/
		public class AStarSearch<TTile>
		{
			public delegate int HeuristicDelegate(TTile from, TTile to);
			public delegate IEnumerable NeighborsDelegate(TTile origin);
			public delegate int CostDelegate(TTile from, TTile to);

			Dictionary<TTile, TTile> cameFrom;
			Dictionary<TTile, int> costSoFar;
			PriorityQueue<int, TTile> frontier;

			HeuristicDelegate Heuristic;
			NeighborsDelegate Neighbors;
			CostDelegate Cost;

			public AStarSearch(HeuristicDelegate heuristic, NeighborsDelegate neighbors, CostDelegate cost)
			{
				if (heuristic == null) { throw new ArgumentNullException("heuristic can't be null!"); }
				if (neighbors == null) { throw new ArgumentNullException("neighbors can't be null!"); }
				if (cost == null) { throw new ArgumentNullException("cost can't be null!"); }

				Heuristic = heuristic;
				Neighbors = neighbors;
				Cost = cost;

				cameFrom = new Dictionary<TTile, TTile>();
				costSoFar = new Dictionary<TTile, int>();
				frontier = new PriorityQueue<int, TTile>();
			}

			public void DoSearch(TTile start, TTile goal, List<TTile> result)
			{
				result.Clear();

				cameFrom.Clear();
				costSoFar.Clear();
				frontier.Clear();

				frontier.Enqueue(0, start);

				cameFrom[start] = start;
				costSoFar[start] = 0;

				TTile current;
				while (frontier.Count > 0)
				{
					current = frontier.DequeueValue();

					if (current.Equals(goal))
					{
						break;
					}

					foreach (TTile next in Neighbors(current))
					{
						int newCost = costSoFar[current] + Cost(current, next);
						if (!costSoFar.ContainsKey(next) || newCost < costSoFar[next])
						{
							costSoFar[next] = newCost;
							int priority = newCost + Heuristic(next, goal);
							frontier.Enqueue(priority, next);
							cameFrom[next] = current;
						}
					}
				}

				current = goal;
				while (cameFrom.ContainsKey(current) && !current.Equals(start))
				{
					result.Add(current);
					current = cameFrom[current];
				}
				if (current.Equals(start))
				{
					result.Add(current);
					result.Reverse();
				}
				else
				{
					result.Clear();
				}
			}
		}
	}

	/*********************************************************************************
	 * Below are the classes that implements the tiles of a generic grid in various  *
	 * coordinate systems (basically hex and quad) along with some utilities.        *
	 *********************************************************************************/
	namespace Tiles
	{
		/********************************************************************
		 * Cube coordinate system for hex grids. Based mainly on the        *
		 * work here: http://www.redblobgames.com/grids/hexagons/.          *
		 * For details about different coordinate systems used on hex grids *
		 * see: http://www.redblobgames.com/grids/hexagons/#coordinates     *
		 ********************************************************************/
		public class CubeCoordHex
		{
			public readonly int x;
			public readonly int y;
			public readonly int z;

			// CONSTRUCTORS

			public CubeCoordHex(CubeCoordHex other)
			{
				x = other.x;
				y = other.y;
				z = other.z;
			}

			public CubeCoordHex(int x, int y, int z)
			{
				if (x + y + z != 0) { throw new ArgumentException(string.Format("Invalid cube coordinates! {0} + {1} + {2} != 0", x, y, z)); }
				this.x = x;
				this.y = y;
				this.z = z;
			}

			public CubeCoordHex(float x, float y, float z)
			{
				// Rounding to the nearest hex

				int rx = Mathf.RoundToInt(x);
				int ry = Mathf.RoundToInt(y);
				int rz = Mathf.RoundToInt(z);

				// However, although x + y + z = 0, after rounding we do not have a guarantee that rx + ry + rz = 0.
				// So we reset the component with the largest change back to what the constraint rx + ry + rz = 0 requires.

				float x_diff = Mathf.Abs(rx - x);
				float y_diff = Mathf.Abs(ry - y);
				float z_diff = Mathf.Abs(rz - z);

				if (x_diff > y_diff && x_diff > z_diff)
				{
					rx = -ry - rz;
				}
				else if (y_diff > z_diff)
				{
					ry = -rx - rz;
				}
				else
				{
					rz = -rx - ry;
				}

				this.x = rx;
				this.y = ry;
				this.z = rz;
			}

			// VALUE EQUALITY

			public override bool Equals(object obj)
			{
				// If parameter is null return false.
				if (obj == null)
				{
					return false;
				}

				// If parameter cannot be cast to CubeCoordHex return false.
				CubeCoordHex cch = obj as CubeCoordHex;
				if ((object)cch == null)
				{
					return false;
				}

				// Return true if the fields match:
				return cch.x == x && cch.y == y && cch.z == z;
			}

			// To enhance performance
			public bool Equals(CubeCoordHex cch)
			{
				// If parameter is null return false.
				if ((object)cch == null)
				{
					return false;
				}

				// Return true if the fields match:
				return cch.x == x && cch.y == y && cch.z == z;
			}

			public override int GetHashCode()
			{
				// Uses the default hash code generator
				return new { x, y, z }.GetHashCode();
			}

			// Redefines operator == since it is an immutable object
			public static bool operator ==(CubeCoordHex a, CubeCoordHex b)
			{
				// If both are null, or both are same instance, return true.
				if (ReferenceEquals(a, b))
				{
					return true;
				}

				// If one is null, but not both, return false.
				if (((object)a == null) || ((object)b == null))
				{
					return false;
				}

				// Return true if the fields match:
				return a.x == b.x && a.y == b.y && a.z == b.z;
			}

			public static bool operator !=(CubeCoordHex a, CubeCoordHex b)
			{
				return !(a == b);
			}

			// CONVERSION OPERATORS

			public static implicit operator Vector3(CubeCoordHex cch)
			{
				return new Vector3(cch.x, cch.y, cch.z);
			}

			// It is explicit because it can cause exceptions, i.e. invalid coordinates
			public static explicit operator CubeCoordHex(Vector3 v)
			{
				return new CubeCoordHex(v.x, v.y, v.z);
			}

			// OTHER OPERATORS

			public static CubeCoordHex operator +(CubeCoordHex a, CubeCoordHex b)
			{
				return new CubeCoordHex(a.x + b.x, a.y + b.y, a.z + b.z);
			}

			public static CubeCoordHex operator -(CubeCoordHex a, CubeCoordHex b)
			{
				return new CubeCoordHex(a.x - b.x, a.y - a.y, a.z - b.z);
			}

			// UTILITY FUNCTIONS

			public static int Distance(CubeCoordHex a, CubeCoordHex b)
			{
				return Mathf.Max(Mathf.Abs(a.x - b.x), Mathf.Abs(a.y - b.y), Mathf.Abs(a.z - b.z));
			}

			public static CubeCoordHex Lerp(CubeCoordHex a, CubeCoordHex b, float t)
			{
				return new CubeCoordHex(Mathf.Lerp(a.x, b.x, t), Mathf.Lerp(a.y, b.y, t), Mathf.Lerp(a.z, b.z, t));
			}

			public static void GetRange(CubeCoordHex origin, int radius, List<CubeCoordHex> result)
			{
				// In the cube coordinate system, each hexagon is a cube in 3D space. Adjacent hexagons are distance 1 apart in the hex grid but distance 2 apart in the cube grid.
				// This makes distances simple: in a square grid, Manhattan distances are abs(dx) + abs(dy), in a cube grid, Manhattan distances are abs(dx) + abs(dy) + abs(dz).
				// The distance on a hex grid is half that; also we note that one of the three coordinates must be the sum of the other two, so we pick that one as the distance.

				result.Clear();

				for (int dx = -radius; dx <= radius; dx++)
				{
					for (int dy = Mathf.Max(-radius, -dx - radius); dy <= Mathf.Min(radius, -dx + radius); dy++)
					{
						int dz = -dx - dy;
						CubeCoordHex delta = new CubeCoordHex(dx, dy, dz);
						result.Add(origin + delta);
					}
				}
			}

			public static void GetLine(CubeCoordHex start, CubeCoordHex end, List<CubeCoordHex> result)
			{
				// Evenly sample the line at dist+1 points, and figure out which hexes those samples are in

				result.Clear();

				int dist = Distance(start, end);

				if (dist == 0)
				{
					result.Add(start);
				}
				else
				{
					// TODO: There are times when cube_lerp will return a point that’s just on the edge between two hexes. Then cube_round will push it one way or the other.
					// The lines will "look better" if it’s always pushed in the same direction. You can do this by adding an “epsilon” hex Cube(1e-6, 1e-6, -2e-6) to one or 
					// both of the endpoints before starting the loop. This will “nudge” the line in one direction to avoid landing on edge boundaries.
					for (int i = 0; i <= dist; i++)
					{
						CubeCoordHex interp = Lerp(start, end, (1.0f / dist) * i);
						result.Add(interp);
					}
				}
			}

			public override string ToString()
			{
				return string.Format("[CubeCoordHex] {0}x{1}x{2}", x, y, z);
			}
		}

		/********************************************************************
		 * Offset coordinate system for hex grids. Based mainly on the      *
		 * work here: http://www.redblobgames.com/grids/hexagons/.          *
		 * For details about different coordinate systems used on hex grids *
		 * see: http://www.redblobgames.com/grids/hexagons/#coordinates     *
		 ********************************************************************/
		 
		// Which rows/columns are offset (to the right/bottom)?
		public enum OffsetHexLayout { OddRow, EvenRow, OddCol, EvenCol }

		public class OffsetCoordHex
		{
			public readonly int x;
			public readonly int y;

			// CONSTRUCTORS

			public OffsetCoordHex(OffsetCoordHex other)
			{
				x = other.x;
				y = other.y;
			}

			public OffsetCoordHex(int x, int y)
			{
				this.x = x;
				this.y = y;
			}

			public OffsetCoordHex(float x, float y)
			{
				// Rounding to the nearest hex
				this.x = Mathf.RoundToInt(x);
				this.y = Mathf.RoundToInt(y);
			}

			// VALUE EQUALITY

			public override bool Equals(object obj)
			{
				// If parameter is null return false.
				if (obj == null)
				{
					return false;
				}

				// If parameter cannot be cast to CubeCoordHex return false.
				OffsetCoordHex cch = obj as OffsetCoordHex;
				if ((object)cch == null)
				{
					return false;
				}

				// Return true if the fields match:
				return cch.x == x && cch.y == y;
			}

			// To enhance performance
			public bool Equals(OffsetCoordHex och)
			{
				// If parameter is null return false.
				if ((object)och == null)
				{
					return false;
				}

				// Return true if the fields match:
				return och.x == x && och.y == y;
			}

			public override int GetHashCode()
			{
				// Uses the default hash code generator
				return new { x, y }.GetHashCode();
			}

			// Redefines operator == since it is an immutable object
			public static bool operator ==(OffsetCoordHex a, OffsetCoordHex b)
			{
				// If both are null, or both are same instance, return true.
				if (ReferenceEquals(a, b))
				{
					return true;
				}

				// If one is null, but not both, return false.
				if (((object)a == null) || ((object)b == null))
				{
					return false;
				}

				// Return true if the fields match:
				return a.x == b.x && a.y == b.y;
			}

			public static bool operator !=(OffsetCoordHex a, OffsetCoordHex b)
			{
				return !(a == b);
			}

			// CONVERSION OPERATORS

			public static implicit operator Vector2(OffsetCoordHex och)
			{
				return new Vector2(och.x, och.y);
			}

			public static implicit operator OffsetCoordHex(Vector2 v)
			{
				return new OffsetCoordHex(v.x, v.y);
			}

			// OTHER OPERATORS

			public static OffsetCoordHex operator +(OffsetCoordHex a, OffsetCoordHex b)
			{
				return new OffsetCoordHex(a.x + b.x, a.y + b.y);
			}

			public static OffsetCoordHex operator -(OffsetCoordHex a, OffsetCoordHex b)
			{
				return new OffsetCoordHex(a.x - b.x, a.y - a.y);
			}

			// UTILITY FUNCTIONS

			public static int Distance(OffsetCoordHex a, OffsetCoordHex b, OffsetHexLayout layout)
			{
				CubeCoordHex aCube = HexGridUtils.ToCubeCoord(a, layout);
				CubeCoordHex bCube = HexGridUtils.ToCubeCoord(b, layout);

				return CubeCoordHex.Distance(aCube, bCube);
			}

			public static OffsetCoordHex Lerp(OffsetCoordHex a, OffsetCoordHex b, float t, OffsetHexLayout layout)
			{
				CubeCoordHex aCube = HexGridUtils.ToCubeCoord(a, layout);
				CubeCoordHex bCube = HexGridUtils.ToCubeCoord(b, layout);

				CubeCoordHex lerpCube = CubeCoordHex.Lerp(aCube, bCube, t);

				return HexGridUtils.ToOffsetCoord(lerpCube, layout);
			}

			public static void GetRange(OffsetCoordHex origin, int radius, List<OffsetCoordHex> result, OffsetHexLayout layout)
			{
				List<CubeCoordHex> resultCube = new List<CubeCoordHex>();
				CubeCoordHex originCube = HexGridUtils.ToCubeCoord(origin, layout);

				CubeCoordHex.GetRange(originCube, radius, resultCube);

				HexGridUtils.ToOffsetCoord(resultCube, layout, result);
			}

			public static void GetLine(OffsetCoordHex start, OffsetCoordHex end, List<OffsetCoordHex> result, OffsetHexLayout layout)
			{
				List<CubeCoordHex> resultCube = new List<CubeCoordHex>();
				CubeCoordHex startCube = HexGridUtils.ToCubeCoord(start, layout);
				CubeCoordHex endCube = HexGridUtils.ToCubeCoord(end, layout);

				CubeCoordHex.GetLine(startCube, endCube, resultCube);

				HexGridUtils.ToOffsetCoord(resultCube, layout, result);
			}

			public override string ToString()
			{
				return string.Format("[OffsetCoordHex] {0}x{1}", x, y);
			}
		}

		/********************************************************************
		 * Utilities to convert coordinate system for hex grids from one    *
		 * system to another. Based mainly on the work here:                *
		 * http://www.redblobgames.com/grids/hexagons/.                     *
		 * For details about hex coordinate systems conversion see:         *
		 * http://www.redblobgames.com/grids/hexagons/#conversions          *
		 ********************************************************************/
		 public class HexGridUtils
		{
			public static CubeCoordHex ToCubeCoord(OffsetCoordHex och, OffsetHexLayout layout)
			{
				switch (layout)
				{
					case OffsetHexLayout.EvenRow:
						{
							int x = och.x - (och.y + (och.y & 1)) / 2;
							int z = och.y;
							int y = -x - z;
							return new CubeCoordHex(x, y, z);
						}
					case OffsetHexLayout.EvenCol:
						{
							int x = och.x;
							int z = och.y - (och.x + (och.x & 1)) / 2;
							int y = -x - z;
							return new CubeCoordHex(x, y, z);
						}
					case OffsetHexLayout.OddCol:
						{
							int x = och.x;
							int z = och.y - (och.x - (och.x & 1)) / 2;
							int y = -x - z;
							return new CubeCoordHex(x, y, z);
						}
					case OffsetHexLayout.OddRow:
						{
							int x = och.x - (och.y - (och.y & 1)) / 2;
							int z = och.y;
							int y = -x - z;
							return new CubeCoordHex(x, y, z);
						}
					default:
						throw new NotImplementedException(string.Format("Layout not implemented: {0}", layout.ToString()));
				}
			}

			public static OffsetCoordHex ToOffsetCoord(CubeCoordHex cch, OffsetHexLayout layout)
			{
				switch (layout)
				{
					case OffsetHexLayout.EvenRow:
						{
							int x = cch.x + (cch.z + (cch.z & 1)) / 2;
							int y = cch.z;
							return new OffsetCoordHex(x, y);
						}
					case OffsetHexLayout.EvenCol:
						{
							int x = cch.x;
							int y = cch.z + (cch.x + (cch.x & 1)) / 2;
							return new OffsetCoordHex(x, y);
						}
					case OffsetHexLayout.OddCol:
						{
							int x = cch.x;
							int y = cch.z + (cch.x - (cch.x & 1)) / 2;
							return new OffsetCoordHex(x, y);
						}
					case OffsetHexLayout.OddRow:
						{
							int x = cch.x + (cch.z - (cch.z & 1)) / 2;
							int y = cch.z;
							return new OffsetCoordHex(x, y);
						}
					default:
						throw new NotImplementedException(string.Format("Layout not implemented: {0}", layout.ToString()));
				}
			}

			public static void ToCubeCoord(List<OffsetCoordHex> ochList, OffsetHexLayout layout, List<CubeCoordHex> result)
			{
				result.Clear();

				foreach (OffsetCoordHex och in ochList)
				{
					result.Add(ToCubeCoord(och, layout));
				}
			}

			public static void ToOffsetCoord(List<CubeCoordHex> cchList, OffsetHexLayout layout, List<OffsetCoordHex> result)
			{
				result.Clear();

				foreach (CubeCoordHex cch in cchList)
				{
					result.Add(ToOffsetCoord(cch, layout));
				}
			}
		}

		/**********************************************************
		 * Coordinate system for quad grids (like checkerboards). *
		 * Things are simpler than with hex boards execpt with    *
		 * the variety of distances that can be defined on them.  *
		 **********************************************************/
		public class Quad
		{
			public static readonly Quad North = new Quad(0, 1);
			public static readonly Quad South = new Quad(0, -1);
			public static readonly Quad East = new Quad(1, 0);
			public static readonly Quad West = new Quad(-1, 0);
			public static readonly Quad NorthEast = North + East;
			public static readonly Quad NorthWest = North + West;
			public static readonly Quad SouthEast = South + East;
			public static readonly Quad SouthWest = South + West;

			public static readonly Quad[] OrthogonalDirections = { North, East, South, West };
			public static readonly Quad[] DiagonalDirections = { NorthEast, SouthEast, SouthWest, NorthWest };
			public static readonly Quad[] AllDirections = { North, NorthEast, East, SouthEast, South, SouthWest, West, NorthWest };

			public readonly int x;
			public readonly int y;

			// CONSTRUCTORS

			public Quad(Quad other)
			{
				x = other.x;
				y = other.y;
			}

			public Quad(int x, int y)
			{
				this.x = x;
				this.y = y;
			}

			public Quad(float x, float y)
			{
				// Rounding to the nearest hex
				this.x = Mathf.RoundToInt(x);
				this.y = Mathf.RoundToInt(y);
			}

			// VALUE EQUALITY

			public override bool Equals(object obj)
			{
				// If parameter is null return false.
				if (obj == null)
				{
					return false;
				}

				// If parameter cannot be cast to CubeCoordHex return false.
				Quad q = obj as Quad;
				if ((object)q == null)
				{
					return false;
				}

				// Return true if the fields match:
				return q.x == x && q.y == y;
			}

			// To enhance performance
			public bool Equals(Quad q)
			{
				// If parameter is null return false.
				// FIXME: do this in the base class...
				if ((object)q == null)
				{
					return false;
				}

				// Return true if the fields match:
				return q.x == x && q.y == y;
			}

			public override int GetHashCode()
			{
				// Uses the default hash code generator
				return new { x, y }.GetHashCode();
			}

			// Redefines operator == since it is an immutable object
			public static bool operator ==(Quad a, Quad b)
			{
				// If both are null, or both are same instance, return true.
				if (ReferenceEquals(a, b))
				{
					return true;
				}

				// If one is null, but not both, return false.
				if (((object)a == null) || ((object)b == null))
				{
					return false;
				}

				// Return true if the fields match:
				return a.x == b.x && a.y == b.y;
			}

			public static bool operator !=(Quad a, Quad b)
			{
				return !(a == b);
			}

			// CONVERSION OPERATORS

			public static implicit operator Vector2(Quad q)
			{
				return new Vector2(q.x, q.y);
			}

			public static implicit operator Quad(Vector3 v)
			{
				return new Quad(v.x, v.y);
			}

			// OTHER OPERATORS

			public static Quad operator +(Quad a, Quad b)
			{
				return new Quad(a.x + b.x, a.y + b.y);
			}

			public static Quad operator -(Quad a, Quad b)
			{
				return new Quad(a.x - b.x, a.y - a.y);
			}

			// UTILITY FUNCTIONS

			public static int ChessboardDistance(Quad a, Quad b)
			{
				return Mathf.Max(Mathf.Abs(a.x - b.x), Mathf.Abs(a.y - b.y));
			}

			public static int ManhattanDistance(Quad a, Quad b)
			{
				return Mathf.Abs(a.x - b.x) + Mathf.Abs(a.y - b.y);
			}

			public static float EuclideanDistance(Quad a, Quad b)
			{
				return Vector2.Distance(a, b);
			}

			public static void GetChessboardRange(Quad origin, int radius, List<Quad> result)
			{
				result.Clear();

				for (int x = -radius; x <= radius; x++)
				{
					for (int y = -radius; y <= radius; y++)
					{
						Quad delta = new Quad(x, y);
						result.Add(origin + delta);
					}
				}
			}

			public static void GetManhattanRange(Quad origin, int radius, List<Quad> result)
			{
				result.Clear();

				for (int x = -radius; x <= radius; x++)
				{
					for (int y = -radius+Mathf.Abs(x); y <= radius-Mathf.Abs(x); y++)
					{
						Quad delta = new Quad(x, y);
						result.Add(origin + delta);
					}
				}
			}

			public static void GetEuclideanRange(Quad origin, int radius, List<Quad> result)
			{
				result.Clear();

				for (int x = -radius; x <= radius; x++)
				{
					float y = -Mathf.Sqrt(radius - x);
					while (y <= Mathf.Sqrt(radius - x))
					{
						Quad delta = new Quad(x, y);
						result.Add(origin + delta);
						y++;
					}
				}
			}

			public static Quad Lerp(Quad a, Quad b, float t)
			{
				return new Quad(Mathf.Lerp(a.x, b.x, t), Mathf.Lerp(a.y, b.y, t));
			}

			// Adjacent points may have just a vertex in common
			public static void GetLineUncostrained(Quad start, Quad end, List<Quad> result)
			{
				result.Clear();

				int dist = ChessboardDistance(start, end);

				if (dist == 0)
				{
					result.Add(start);
				}
				else
				{
					for (int i = 0; i <= dist; i++)
					{
						result.Add(Lerp(start, end, (float)i / dist));
					}
				}
			}

			// Draw a line but only making orthogonal steps, i.e. adjacent points will always have a side in common
			public static void GetLineOnlyOrthogonalSteps(Quad start, Quad end, List<Quad> result)
			{
				result.Clear();

				int dx = end.x - start.x;
				int dy = end.y - start.y;

				int nx = Mathf.Abs(dx);
				int ny = Mathf.Abs(dy);

				int signX = dx > 0 ? 1 : -1;
				int signY = dy > 0 ? 1 : -1;

				result.Add(start);
				int ix = 0;
				int iy = 0;
				int qx = start.x;
				int qy = start.y;
				while (ix < nx || iy < ny)
				{
					if ((0.5f + ix) / nx < (0.5f + iy) / ny)
					{
						// next step is horizontal
						qx += signX;
						ix++;
					}
					else
					{
						// next step is vertical
						qy += signY;
						iy++;
					}
					result.Add(new Quad(qx, qy));
				}
			}

			// Supercover lines catch all the grid squares that a line passes through.
			// We can take a diagonal step only if the line passes exactly through the corner.
			public static void GetLineSupercover(Quad start, Quad end, List<Quad> result)
			{
				result.Clear();

				int dx = end.x - start.x;
				int dy = end.y - start.y;

				int nx = Mathf.Abs(dx);
				int ny = Mathf.Abs(dy);

				int signX = dx > 0 ? 1 : -1;
				int signY = dy > 0 ? 1 : -1;

				result.Add(start);
				int ix = 0;
				int iy = 0;
				int qx = start.x;
				int qy = start.y;
				while (ix < nx || iy < ny)
				{
					if ((1 + 2 * ix) * ny == (1 + 2 * iy) * nx)
					{
						// next step is diagonal
						qx += signX;
						qy += signY;
						ix++;
						iy++;
					}
					else if ((0.5f + ix) / nx < (0.5f + iy) / ny)
					{
						// next step is horizontal
						qx += signX;
						ix++;
					}
					else
					{
						// next step is vertical
						qy += signY;
						iy++;
					}
					result.Add(new Quad(qx, qy));
				}
			}

			public override string ToString()
			{
				return string.Format("[Quad] {0}x{1}", x, y);
			}
		}
	}

	namespace AI
	{
		/******************************************************************************* 
		 * Influence maps based on a generic grid (hex or quad).                       *
		 * See http://gameschoolgems.blogspot.it/2009/12/influence-maps-i.html and     *
		 * http://www.redblobgames.com/x/1510-influence-maps/ for a brief introduction *
		 * on influence maps and their use for gameplay AI.                            *
		 *******************************************************************************/
		public class InfluenceMap<TTile>
		{
			public struct InfluenceMapPoint
			{
				public TTile coord;
				public float val;

				public InfluenceMapPoint(TTile c, float v)
				{
					coord = c;
					val = v;
				}
			}

			List<InfluenceMapPoint> map;

			public InfluenceMap()
			{
				map = new List<InfluenceMapPoint>();
			}

			public InfluenceMap(IEnumerable<TTile> mapTiles, float startVal = 0)
				: this()
			{
				SetTiles(mapTiles, startVal);
			}

			public InfluenceMap(List<InfluenceMapPoint> points)
				: this()
			{
				SetPoints(points);
			}

			public InfluenceMap(InfluenceMap<TTile> other)
				: this()
			{
				map.AddRange(other.map);
			}

			public int Count { get { return map.Count; } }

			public InfluenceMapPoint this[int i]
			{
				get { return map[i]; }
			}

			public float this[TTile t]
			{
				get
				{
					int index = map.FindIndex((p) => p.coord.Equals(t));
					return map[index].val;
				}

				set
				{
					int index = map.FindIndex((p) => p.coord.Equals(t));
					map[index] = new InfluenceMapPoint(map[index].coord, value);
				}
			}

			public IEnumerable<TTile> Tiles
			{
				get
				{
					foreach (InfluenceMapPoint p in map)
					{
						yield return p.coord;
					}
				}
			}

			public void Reset(float val = 0.0f)
			{
				for (int i = 0; i < map.Count; i++)
				{
					map[i] = new InfluenceMapPoint(map[i].coord, val);
				}
			}

			public void SetTiles(IEnumerable<TTile> pMapCoords, float startVal = 0)
			{
				map.Clear();
				foreach (TTile c in pMapCoords)
				{
					map.Add(new InfluenceMapPoint(c, startVal));
				}
			}

			public void SetPoints(List<InfluenceMapPoint> points)
			{
				map.Clear();
				foreach (InfluenceMapPoint p in points)
				{
					map.Add(p);
				}
			}

			// Lerp(oldMap, newMap, momentum)
			// Propagation function: newInfluenceOnPoint = propagationFunction(influenceOrigin, influenceOriginValue, pointToUpdate)
			public void Update(IEnumerable<InfluenceMapPoint> influencePoints, System.Func<TTile, float, TTile, float> propagationFunction, float momentum = 1.0f)
			{
				float[] newValues = new float[map.Count];

				foreach (InfluenceMapPoint p in influencePoints)
				{
					for (int i = 0; i < map.Count; i++)
					{
						newValues[i] += propagationFunction(p.coord, p.val, map[i].coord);
					}
				}

				for (int i = 0; i < map.Count; i++)
				{
					map[i] = new InfluenceMapPoint(map[i].coord, Mathf.Lerp(map[i].val, newValues[i], momentum));
				}
			}

			public void GetMapPoints(List<InfluenceMapPoint> points)
			{
				points.Clear();
				points.AddRange(map);
			}

			public void Add(InfluenceMap<TTile> other)
			{
				DoOperation(other, (xVal, yVal) => xVal + yVal);
			}

			public void Sub(InfluenceMap<TTile> other)
			{
				DoOperation(other, (xVal, yVal) => xVal - yVal);
			}

			public void Abs()
			{
				DoOperation((v) => Mathf.Abs(v));
			}

			void DoOperation(System.Func<float, float> operation)
			{
				for (int i = 0; i < map.Count; i++)
				{
					map[i] = new InfluenceMapPoint(map[i].coord, operation(map[i].val));
				}
			}

			void DoOperation(InfluenceMap<TTile> other, System.Func<float, float, float> operation)
			{
				HashSet<TTile> tiles = new HashSet<TTile>(Tiles);
				tiles.IntersectWith(other.Tiles);
				foreach (TTile t in tiles)
				{
					this[t] = operation(this[t], other[t]);
				}
			}
		}
	}

	/**************************************************************
     * Finally, the actual implementation of a grid based on the  *
	 * structures defined above. There's an abstract grid that is *
	 * agnostic of the tile coordinate system and a quad grid     *
	 * concrete implementation. Unfortunately I didn't had the    *
	 * time yet to add an hex grid implementation.                *
	 **************************************************************/
	
	public abstract class Grid<TTile, TContent>
	{
		protected Vector2 offset;
		protected Vector2 extents;

		protected Dictionary<TTile, TContent> tiles;

		public Grid(Vector2 offset, Vector2 extents)
		{
			if (extents.x <= 0 || extents.y <= 0)
			{
				throw new Exception(string.Format("Invalid extents: {0}. Must be both greater than 0.", extents));
			}

			this.offset = offset;
			this.extents = extents;

			tiles = new Dictionary<TTile, TContent>();
		}

		public abstract TTile Neighbor(TTile origin, TTile direction);

		public void Neighbors(TTile origin, IEnumerable<TTile> directions, List<TTile> result)
		{
			result.Clear();

			foreach (TTile d in directions)
			{
				TTile n = Neighbor(origin, d);
				if (IsValid(n))
				{
					result.Add(Neighbor(origin, d));
				}
			}
		}

		public bool IsValid(TTile tile)
		{
			return tile != null && tiles.ContainsKey(tile);
		}

		public TContent GetTileContent(TTile tile)
		{
			TContent result;
			tiles.TryGetValue(tile, out result);
			return result;
		}

		public TContent this[TTile key]
		{
			get
			{
				return tiles[key];
			}

			set
			{
				tiles[key] = value;
			}
		}

		public IEnumerable<TTile> Tiles
		{
			get
			{
				foreach (TTile t in tiles.Keys)
				{
					yield return t;
				}
			}
		}

		public IEnumerable<TContent> Contents
		{
			get
			{
				foreach (TTile t in tiles.Keys)
				{
					yield return tiles[t];
				}
			}
		}

		protected void AStarSearch(TTile start, TTile goal, Utils.AStarSearch<TTile>.HeuristicDelegate heuristic, Utils.AStarSearch<TTile>.NeighborsDelegate neighbors, Utils.AStarSearch<TTile>.CostDelegate cost, List<TTile> result)
		{
			Utils.AStarSearch<TTile> search = new Utils.AStarSearch<TTile>(heuristic, neighbors, cost);
			search.DoSearch(start, goal, result);
		}
	}

	public class QuadGrid<TContent> : Grid<Quad, TContent>
	{
		public QuadGrid(Quad offset, Vector2 extents) : base(offset, extents)
		{
			int maxX = Mathf.RoundToInt(extents.x - offset.x);
			int maxY = Mathf.RoundToInt(extents.y - offset.y);
			int minX = -Mathf.RoundToInt(extents.x - offset.x);
			int minY = -Mathf.RoundToInt(extents.y - offset.y);

			for (int x = minX; x <= maxX; x++)
			{
				for (int y = minY; y <= maxY; y++)
				{
					tiles.Add(new Quad(x, y), default(TContent));
				}
			}
		}

		public override Quad Neighbor(Quad origin, Quad direction)
		{
			Quad n = origin + direction;
			if (!IsValid(n))
			{
				n = null;
			}
			return n;
		}

		protected void AStarSearchManhattan(Quad start, Quad goal, AStarSearchQuad.CostDelegate cost, List<Quad> result)
		{
			AStarSearchQuad.HeuristicDelegate heuristic = (from, to) =>
			{
				return Quad.ManhattanDistance(from, to);
			};

			AStarSearchQuad.NeighborsDelegate neighbors = (origin) =>
			{
				List<Quad> ns = new List<Quad>();
				Neighbors(origin, Quad.OrthogonalDirections, ns);
				return ns;
			};

			AStarSearch(start, goal, heuristic, neighbors, cost, result);
		}

		void AStarSearchChessboard(Quad start, Quad goal, AStarSearchQuad.CostDelegate cost, List<Quad> result)
		{
			AStarSearchQuad.HeuristicDelegate heuristic = (from, to) =>
			{
				return Quad.ChessboardDistance(from, to);
			};

			AStarSearchQuad.NeighborsDelegate neighbors = (origin) =>
			{
				List<Quad> ns = new List<Quad>();
				Neighbors(origin, Quad.AllDirections, ns);
				return ns;
			};

			AStarSearch(start, goal, heuristic, neighbors, cost, result);
		}
	}
}
